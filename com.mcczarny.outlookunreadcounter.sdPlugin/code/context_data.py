from enum import Enum
from dataclasses import dataclass
from tile_visualizer import TileVisualizer, SimpleVisualizer, ExtraInfoVisualizer, AnimatedExtraInfoVisualizer
from streamdeck_sdk import logger


class ExtraInfoStates(str, Enum):
    NONE = "None"
    SENDER = "Sender"
    SUBJECT = "Subject"
    BOTH = "Both"


@dataclass(init=False)
class ContextData:
    account: str
    extra_info: ExtraInfoStates = ExtraInfoStates.NONE
    animated: bool = False
    set_state_callback: callable
    set_title_callback: callable
    tile_visualizer: TileVisualizer

    def __init__(
        self,
        account: str,
        extra_info: ExtraInfoStates,
        animated: bool,
        set_state_callback: callable,
        set_title_callback: callable,
    ):
        self.account = account
        self.extra_info = extra_info
        self.animated = animated
        self.set_state_callback = set_state_callback
        self.set_title_callback = set_title_callback
        self.tile_visualizer = None

        self.__post_init__()

    def _update_tile_visualizer(self):
        if self.tile_visualizer is not None:
            self.tile_visualizer.stop()

        if self.extra_info == ExtraInfoStates.NONE:
            logger.debug(f"[{self.account}] Updating tile visualizer to SimpleVisualizer")
            self.tile_visualizer = SimpleVisualizer(self.set_state_callback, self.set_title_callback)
        else:
            show_sender = self.extra_info in [ExtraInfoStates.SENDER, ExtraInfoStates.BOTH]
            show_subject = self.extra_info in [ExtraInfoStates.SUBJECT, ExtraInfoStates.BOTH]
            if not self.animated:
                logger.debug(f"[{self.account}] Updating tile visualizer to ExtraInfoVisualizer")
                self.tile_visualizer = ExtraInfoVisualizer(
                    self.set_state_callback, self.set_title_callback, show_sender, show_subject
                )
            else:
                logger.debug(f"[{self.account}] Updating tile visualizer to AnimatedExtraInfoVisualizer")
                self.tile_visualizer = AnimatedExtraInfoVisualizer(
                    self.set_state_callback, self.set_title_callback, show_sender, show_subject
                )

    def __post_init__(self):
        if not isinstance(self.account, str) or not self.account:
            raise ValueError("Account must be a non-empty string")
        if not isinstance(self.extra_info, ExtraInfoStates):
            raise ValueError("Extra info must be an instance of ExtraInfoStates")
        if not isinstance(self.animated, bool):
            raise ValueError("Animated must be a boolean")
        if not callable(self.set_state_callback):
            raise ValueError("Set state callback must be a callable")
        if not callable(self.set_title_callback):
            raise ValueError("Set title callback must be a callable")
        self._update_tile_visualizer()

    def set_extra_info(self, extra_info: ExtraInfoStates | str):
        if extra_info is None or extra_info == "":
            extra_info = ExtraInfoStates.NONE
        if not isinstance(extra_info, ExtraInfoStates):
            extra_info = ExtraInfoStates(extra_info)
        if self.extra_info == extra_info:
            return
        self.extra_info = extra_info
        self._update_tile_visualizer()

    def set_animated(self, animated: bool | str):
        logger.debug(f"[{self.account}] Received animated: {animated}")
        if isinstance(animated, str) and animated.lower() == "false":
            animated = False

        animated = bool(animated)
        if self.animated == animated:
            return
        logger.debug(f"[{self.account}] Setting animated to {animated}")
        self.animated = animated
        self._update_tile_visualizer()
