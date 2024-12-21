import settings
import threading
from enum import IntEnum, Enum
from dataclasses import dataclass

from streamdeck_sdk import StreamDeck, Action, events_received_objs, logger, log_errors, in_separate_thread
import win32com.client


class MailStates(IntEnum):
    READ = 0
    UNREAD = 1


class ExtraInfoStates(str, Enum):
    NONE = "None"
    SENDER = "Sender"
    SUBJECT = "Subject"
    BOTH = "Both"


@dataclass
class ContextData:
    account: str
    extra_info: ExtraInfoStates
    animated: bool = False
    animation_index: int = 1


class UnreadCounter(Action):

    UUID = "com.mcczarny.outlookunreadcounter.unreadcounter"
    MAIL_COUNT_UPDATE_INTERVAL: float = 10
    ACCOUNT_KEY = "account"
    ACCOUNTS_KEY = "accounts"
    EXTRA_INFO_KEY = "extra_info"
    EXTRA_INFO_STATES_KEY = "extra_info_states"
    EXTRA_INFO_MAX_LENGTH = 10

    wake_event = threading.Event()

    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    monitor_outlook = None
    context = ""
    context_data = {}  # Will store ContextData objects

    def set_accounts_settings(self, context: str, settings: dict):
        logger.debug(f"[{context}] set_accounts_settings: {settings}")
        accounts = [acc.DisplayName for acc in self.outlook.Stores]

        current_account = settings.get(self.ACCOUNT_KEY) if self.ACCOUNT_KEY in settings else accounts[0] if accounts else ""
        current_extra_info = settings.get(self.EXTRA_INFO_KEY, ExtraInfoStates.NONE)

        if current_extra_info not in [state.value for state in ExtraInfoStates]:
            current_extra_info = ExtraInfoStates.NONE

        self.context_data[context] = ContextData(account=current_account, extra_info=current_extra_info)

        payload = {
            self.ACCOUNT_KEY: self.context_data[context].account,
            self.ACCOUNTS_KEY: accounts,
            self.EXTRA_INFO_KEY: self.context_data[context].extra_info,
            self.EXTRA_INFO_STATES_KEY: [state.value for state in ExtraInfoStates],
        }
        self.set_settings(context=context, payload=payload)

    @log_errors
    def on_will_appear(self, obj: events_received_objs.WillAppear):
        logger.debug(f"on_will_appear: {obj.context}")
        self.set_title(context=obj.context, title="Loading...")
        self.set_state(context=obj.context, state=MailStates.UNREAD)

        self.set_accounts_settings(obj.context, obj.payload.settings)

    def update_unread_count(self, outlook, context: str):
        data = self.context_data[context]
        logger.debug(f"update_unread_count: {context} account: {data.account}")
        if not data.account:
            logger.debug(f"No account set, skipping...")
            return
        unread_count = "?"
        extra_info = ""
        folder = outlook.Stores(data.account).GetDefaultFolder(6) if data.account else outlook.GetDefaultFolder(6)

        logger.debug(f"account: {data.account}")
        unread_count = folder.UnReadItemCount
        if unread_count > 0:
            logger.debug(f"Unread count is bigger than 0, processing extra info...")
            try:
                last_unread_email = folder.Items.Restrict("[UnRead] = True").GetLast()
                if data.extra_info in [ExtraInfoStates.SENDER, ExtraInfoStates.BOTH]:
                    logger.debug(f"sender")
                    sender_name = last_unread_email.SenderName
                    if len(sender_name) > self.EXTRA_INFO_MAX_LENGTH:
                        logger.debug(f"sender name ({sender_name}) is too long, truncating...")
                        # Using vertical ellipsis to save space while indicating that the text is truncated
                        sender_name = sender_name[: self.EXTRA_INFO_MAX_LENGTH - 3] + "..."
                    extra_info = sender_name
                if data.extra_info in [ExtraInfoStates.SUBJECT, ExtraInfoStates.BOTH]:
                    logger.debug(f"subject")
                    if extra_info != "":
                        extra_info += "\n"
                    subject = last_unread_email.Subject
                    if len(subject) > self.EXTRA_INFO_MAX_LENGTH:
                        logger.debug(f"subject ({subject}) is too long, truncating...")
                        subject = subject[: self.EXTRA_INFO_MAX_LENGTH - 3] + "..."
                    extra_info += subject
            except Exception as e:
                logger.error(f"Error getting extra info: {e}")
            logger.debug(f"extra_info: [{extra_info}]")
        state = MailStates.UNREAD if unread_count > 0 else MailStates.READ
        logger.debug(f"unread_count: {unread_count} extra_info: {extra_info} state: {state}")
        self.set_state(context=context, state=state)

        title_content = f"{unread_count}" if extra_info == "" else f"{unread_count}\n{extra_info}"
        logger.debug(f"title_content: {title_content}")
        self.set_title(context=context, title=title_content)

    @log_errors
    def on_did_receive_settings(self, obj: events_received_objs.DidReceiveSettings):
        logger.debug(f"on_did_receive_settings: {obj.payload}")
        update_tiles = False
        if obj.payload.settings.get(self.ACCOUNT_KEY):
            self.context_data[obj.context].account = obj.payload.settings.get(self.ACCOUNT_KEY)
            update_tiles = True

        if obj.payload.settings.get(self.EXTRA_INFO_KEY):
            self.context_data[obj.context].extra_info = obj.payload.settings.get(self.EXTRA_INFO_KEY)
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
            for context in self.context_data:
                data = self.context_data.get(context)
                try:
                    logger.debug(f"run_monitoring: {context} {data.account}")
                    self.update_unread_count(outlook=self.monitor_outlook, context=context)
                except win32com.client.pywintypes.com_error as err:
                    logger.exception(err)
                    logger.debug(f"run_monitoring: {context} {data.account} - restarting monitoring")
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
