import settings
import threading
from enum import IntEnum, Enum

from streamdeck_sdk import StreamDeck, Action, events_received_objs, logger, log_errors, in_separate_thread
import win32com.client


class MailStates(IntEnum):
    READ = 0
    UNREAD = 1

class SecondRowStates(str, Enum):
    NONE = "None"
    SENDER = "Sender"
    SUBJECT = "Subject"

class UnreadCounter(Action):

    UUID = "com.mcczarny.outlookunreadcounter.unreadcounter"
    MAIL_COUNT_UPDATE_INTERVAL: float = 10
    ACCOUNT_KEY = "account"
    ACCOUNTS_KEY = "accounts"
    SECOND_ROW_KEY = "second_row"
    SECOND_ROW_STATES_KEY = "second_row_states"

    wake_event = threading.Event()

    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    monitor_outlook = None
    context = ""
    context_to_account = {}
    context_to_second_row = {}

    def set_accounts_settings(self, context: str, settings: dict):
        logger.debug(f"[{context}] set_accounts_settings: {settings}")
        accounts = [acc.DisplayName for acc in self.outlook.Stores]
        logger.debug(f"[{context}] accounts: {accounts}")
        if self.ACCOUNT_KEY in settings:
            logger.debug(f"[{context}] Using account from the settings: {settings.get(self.ACCOUNT_KEY)}")
            self.context_to_account[context] = settings.get(self.ACCOUNT_KEY)
        
        if self.SECOND_ROW_KEY in settings:
            logger.debug(f"[{context}] Using second_row_state from the settings: {settings.get(self.SECOND_ROW_KEY)}")
            self.context_to_second_row[context] = settings.get(self.SECOND_ROW_KEY)

        if context not in self.context_to_account or self.context_to_account[context] not in accounts:
            self.context_to_account[context] = accounts[0] if len(accounts) > 0 else ""
            logger.debug(f"[{context}] Setting account to: {self.context_to_account[context]}")
        
        if context not in self.context_to_second_row or self.context_to_second_row[context] not in [state.value for state in SecondRowStates]:
            logger.debug(
                f"[{context}] Setting second_row_state to: {self.context_to_second_row[context]}."
                + f"Old value: {self.context_to_second_row.get(context)}")
            self.context_to_second_row[context] = SecondRowStates.NONE
        payload = {
            self.ACCOUNT_KEY: self.context_to_account[context],
            self.ACCOUNTS_KEY: accounts,
            self.SECOND_ROW_KEY: self.context_to_second_row[context],
            self.SECOND_ROW_STATES_KEY: [state.value for state in SecondRowStates],
        }
        self.set_settings(context=context, payload=payload)
    @log_errors
    def on_will_appear(self, obj: events_received_objs.WillAppear):
        logger.debug(f"on_will_appear: {obj.context}")
        self.set_accounts_settings(obj.context, obj.payload.settings)

    def update_unread_count(self, outlook, context: str, account: str):
        logger.debug(f"update_unread_count: {context} account: {account}")
        unread_count = "?"
        second_row = ""
        folder = outlook.Stores(account).GetDefaultFolder(6) if account else outlook.GetDefaultFolder(6)

        logger.debug(f"account: {account}")
        unread_count = folder.UnReadItemCount
        if unread_count > 0:
            logger.debug(f"Unread count is bigger than 0, processing second row...")
            try:
                if self.context_to_second_row[context] == SecondRowStates.SENDER:
                    logger.debug(f"sender")
                    second_row = folder.Items(1).SenderName
                elif self.context_to_second_row[context] == SecondRowStates.SUBJECT:
                    logger.debug(f"subject")
                    second_row = folder.Items(1).Subject
            except:
                logger.error(f"Error getting second row")
            logger.debug(f"second_row: [{second_row}]")
        state = MailStates.UNREAD if unread_count > 0 else MailStates.READ
        logger.debug(f"unread_count: {unread_count} second_row: {second_row} state: {state}")
        self.set_state(context=context, state=state)

        title_content = f"{unread_count}" if second_row == "" else f"{unread_count}\n{second_row}"
        self.set_title(context=context, title=f"{title_content}")

    @log_errors
    def on_did_receive_settings(self, obj: events_received_objs.DidReceiveSettings):
        logger.debug(f"on_did_receive_settings: {obj.payload}")
        update_tiles = False
        if obj.payload.settings.get(self.ACCOUNT_KEY):
            self.context_to_account[obj.context] = obj.payload.settings.get(self.ACCOUNT_KEY)
            update_tiles = True
        
        if obj.payload.settings.get(self.SECOND_ROW_KEY):
            self.context_to_second_row[obj.context] = obj.payload.settings.get(self.SECOND_ROW_KEY)
            update_tiles = True

        if update_tiles:
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
