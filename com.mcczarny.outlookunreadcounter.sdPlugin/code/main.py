import settings
import threading

from streamdeck_sdk import StreamDeck, Action, events_received_objs, logger, log_errors, in_separate_thread
import win32com.client
from context_data import ExtraInfoStates, ContextData
from mail_states import MailStates


class UnreadCounter(Action):
    UUID = "com.mcczarny.outlookunreadcounter.unreadcounter"
    MAIL_COUNT_UPDATE_INTERVAL: float = 10
    ACCOUNT_KEY = "account"
    ACCOUNTS_KEY = "accounts"
    EXTRA_INFO_KEY = "extra_info"
    EXTRA_INFO_STATES_KEY = "extra_info_states"
    ANIMATE_EXTRA_INFO_KEY = "animate_extra_info"

    wake_event = threading.Event()

    outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace("MAPI")
    monitor_outlook = None
    context = ""
    context_data: dict[str, ContextData] = {}  # Will store ContextData objects

    def set_accounts_settings(self, context: str, settings: dict):
        logger.debug(f"[{context}] set_accounts_settings: {settings}")
        accounts = [acc.DisplayName for acc in self.outlook.Stores]

        current_account = (
            settings.get(self.ACCOUNT_KEY)
            if self.ACCOUNT_KEY in settings
            else accounts[0] if accounts else ""
        )
        current_extra_info = settings.get(self.EXTRA_INFO_KEY, ExtraInfoStates.NONE)

        if current_extra_info not in [state.value for state in ExtraInfoStates]:
            current_extra_info = ExtraInfoStates.NONE
        else:
            current_extra_info = ExtraInfoStates(current_extra_info)

        current_animated = settings.get(self.ANIMATE_EXTRA_INFO_KEY, False)

        if context not in self.context_data:
            set_state_callback = lambda state: self.set_state(context=context, state=state)
            set_title_callback = lambda title: self.set_title(context=context, title=title)

            self.context_data[context] = ContextData(
                account=current_account,
                extra_info=current_extra_info,
                animated=current_animated,
                set_state_callback=set_state_callback,
                set_title_callback=set_title_callback,
            )
        else:
            self.context_data[context].account = current_account
            self.context_data[context].extra_info = current_extra_info

        payload = {
            self.ACCOUNT_KEY: self.context_data[context].account,
            self.ACCOUNTS_KEY: accounts,
            self.EXTRA_INFO_KEY: self.context_data[context].extra_info,
            self.EXTRA_INFO_STATES_KEY: [state.value for state in ExtraInfoStates],
        }
        self.set_settings(context=context, payload=payload)
        self.wake_event.set()

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
        folder = (
            outlook.Stores(data.account).GetDefaultFolder(6) if data.account else outlook.GetDefaultFolder(6)
        )

        logger.debug(f"account: {data.account}")
        self.context_data[context].tile_visualizer.update_tile(folder)

    @log_errors
    def on_did_receive_settings(self, obj: events_received_objs.DidReceiveSettings):
        logger.debug(f"on_did_receive_settings: {obj.payload}")
        update_tiles = False
        if obj.payload.settings.get(self.ACCOUNT_KEY):
            self.context_data[obj.context].account = obj.payload.settings.get(self.ACCOUNT_KEY)
            update_tiles = True

        if obj.payload.settings.get(self.EXTRA_INFO_KEY):
            self.context_data[obj.context].set_extra_info(obj.payload.settings.get(self.EXTRA_INFO_KEY))
            update_tiles = True

        animate_extra_info = obj.payload.settings.get(self.ANIMATE_EXTRA_INFO_KEY)
        if animate_extra_info is not None:
            self.context_data[obj.context].set_animated(animate_extra_info)
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
            for context in list(self.context_data.keys()):
                data = self.context_data.get(context)
                try:
                    logger.debug(f"run_monitoring: {context} {data.account}")
                    self.update_unread_count(outlook=self.monitor_outlook, context=context)
                except win32com.client.pywintypes.com_error as err:
                    logger.exception(err)
                    logger.debug(f"run_monitoring: {context} {data.account} - restarting monitoring")
                    self.monitor_outlook = win32com.client.Dispatch("Outlook.Application").GetNamespace(
                        "MAPI"
                    )
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
