import settings
import threading
import time
from enum import IntEnum

from streamdeck_sdk import StreamDeck, Action, events_received_objs, logger, log_errors, in_separate_thread
import win32com.client


class MailStates(IntEnum):
    READ = 0
    UNREAD = 1


class UnreadCounter(Action):

    UUID = "com.mcczarny.outlookunreadcounter.unreadcounter"
    MAIL_COUNT_UPDATE_INTERVAL: float = 10
    wake_event = threading.Event()

    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    monitor_outlook = None
    context = ""
    context_to_account = {}

    def set_accounts_settings(self, context: str, settings: dict):
        logger.debug(f"[{context}] set_accounts_settings")
        accounts = [acc.DisplayName for acc in self.outlook.Stores]
        logger.debug(f"[{context}] accounts: {accounts}")
        if "account" in settings:
            logger.debug(f"[{context}] Using account from the settings: {settings.get('account')}")
            self.context_to_account[context] = settings.get("account")

        if context not in self.context_to_account or self.context_to_account[context] not in accounts:
            self.context_to_account[context] = accounts[0] if len(accounts) > 0 else ""
            logger.debug(f"[{context}] Setting account to: {self.context_to_account[context]}")
        self.set_settings(context=context, payload={"account": self.context_to_account[context], "accounts": accounts})

    @log_errors
    def on_will_appear(self, obj: events_received_objs.WillAppear):
        logger.debug(f"on_will_appear: {obj.context}")
        self.set_accounts_settings(obj.context, obj.payload.settings)

    def update_unread_count(self, outlook, context: str, account: str):
        logger.debug(f"update_unread_count: {context} account: {account}")
        unread_count = "?"
        if account:
            logger.debug(f"account: {account}")
            unread_count = outlook.Stores(account).GetDefaultFolder(6).UnReadItemCount
        else:
            logger.debug(f"default folder")
            unread_count = outlook.GetDefaultFolder(6).UnReadItemCount
        state = MailStates.UNREAD if unread_count > 0 else MailStates.READ
        logger.debug(f"unread_count: {unread_count} state: {state}")
        self.set_state(context=context, state=state)
        self.set_title(context=context, title=f"{unread_count}")

    @log_errors
    def on_did_receive_settings(self, obj: events_received_objs.DidReceiveSettings):
        logger.debug(f"on_did_receive_settings: {obj.payload}")
        if obj.payload.settings.get("account"):
            self.context_to_account[obj.context] = obj.payload.settings.get("account")
            self.wake_event.set()

    @log_errors
    def on_key_down(self, _: events_received_objs.KeyDown):
        pass

    @log_errors
    def on_key_up(self, _: events_received_objs.KeyUp):
        self.wake_event.set()

    @in_separate_thread(daemon=True)
    @log_errors
    def run_monitoring(self):
        logger.debug(f"Starting monitoring...")
        self.monitor_outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
        while True:
            self.wake_event.wait(timeout=self.MAIL_COUNT_UPDATE_INTERVAL)
            for context in self.context_to_account:
                account = self.context_to_account.get(context)
                try:
                    logger.debug(f"run_monitoring: {context} {account}")
                    self.update_unread_count(outlook=self.monitor_outlook, context=context, account=account)
                except win32com.client.pywintypes.com_error as err:
                    logger.exception(err)
                    logger.debug(f"run_monitoring: {context} {account} - restarting monitoring")
                    self.monitor_outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
                except Exception as err:
                    logger.exception(err)
            self.wake_event.clear()

if __name__ == "__main__":
    unread_counter = UnreadCounter()
    unread_counter.run_monitoring()
    StreamDeck(
        actions=[
            unread_counter,
        ],
        log_file=settings.LOG_FILE_PATH,
        log_level=settings.LOG_LEVEL,
        log_backup_count=1,
    ).run()
