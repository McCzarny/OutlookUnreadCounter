from enum import Enum
from dataclasses import dataclass

class ExtraInfoStates(str, Enum):
    NONE = "None"
    SENDER = "Sender"
    SUBJECT = "Subject"
    BOTH = "Both"

@dataclass
class ContextData:
    account: str
    extra_info: ExtraInfoStates = ExtraInfoStates.NONE
    animated: bool = False
    animation_index: int = 1

    def __post_init__(self):
        if not isinstance(self.account, str) or not self.account:
            raise ValueError("Account must be a non-empty string")
        if not isinstance(self.extra_info, ExtraInfoStates):
            raise ValueError("Extra info must be an instance of ExtraInfoStates")
        if not isinstance(self.animated, bool):
            raise ValueError("Animated must be a boolean")
        if not isinstance(self.animation_index, int) or self.animation_index < 1:
            raise ValueError("Animation index must be a positive integer")
