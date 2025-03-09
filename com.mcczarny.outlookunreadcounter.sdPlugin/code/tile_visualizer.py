from abc import ABC, abstractmethod
import win32com.client
from mail_states import MailStates
from streamdeck_sdk import logger, log_errors
import time
import threading


class TileVisualizer(ABC):

    def __init__(self, set_state_callback: callable, set_title_callback: callable):
        self.set_state_callback = set_state_callback
        self.set_title_callback = set_title_callback

    def set_state(self, state: MailStates) -> None:
        self.set_state_callback(state)

    def set_title(self, title: str) -> None:
        self.set_title_callback(title)

    def update_state(self, unread_count: int) -> None:
        self.set_state(MailStates.UNREAD if unread_count > 0 else MailStates.READ)

    @abstractmethod
    def update_tile(self, folder: win32com.client.CDispatch) -> None:
        pass

    def stop(self) -> None:
        pass


class SimpleVisualizer(TileVisualizer):
    def __init__(self, set_state_callback: callable, set_title_callback: callable):
        super().__init__(set_state_callback, set_title_callback)

    def update_tile(self, folder: win32com.client.CDispatch) -> None:
        unread_count = folder.UnReadItemCount
        self.update_state(unread_count)
        self.set_title(f"{unread_count}")


EXTRA_INFO_MAX_LENGTH = 9


class ExtraInfoVisualizer(SimpleVisualizer):
    def __init__(
        self,
        set_state_callback: callable,
        set_title_callback: callable,
        show_sender: bool,
        show_subject: bool,
    ):
        super().__init__(set_state_callback, set_title_callback)
        self.show_sender = show_sender
        self.show_subject = show_subject

    def update_tile(self, folder: win32com.client.CDispatch) -> None:
        unread_count = folder.UnReadItemCount
        if unread_count == 0:
            super().update_tile(folder)
        else:
            self.set_state(MailStates.UNREAD)

            last_unread_email = folder.Items.Restrict("[UnRead] = True").GetLast()
            sender = last_unread_email.SenderName
            subject = last_unread_email.Subject

            extra_info = ""
            if self.show_sender:
                extra_info = self.get_extra_info_line(sender)

            if self.show_subject:
                if extra_info != "":
                    extra_info += "\n"
                subject_text = self.get_extra_info_line(subject)
                extra_info += subject_text

            title_content = f"{unread_count}" if extra_info == "" else f"{unread_count}\n{extra_info}"
            self.set_title(title_content)

    def get_extra_info_line(self, text: str):
        logger.debug(f"get_extra_info_line: {text}")
        return text[:EXTRA_INFO_MAX_LENGTH]


class AnimatedExtraInfoVisualizer(ExtraInfoVisualizer):
    class TileAnimation:
        def __init__(self, set_title: callable, unread_count: int, sender: str, subject: str):
            # TODO: Move it to single place with update interval
            self.FIRST_FRAME_DURATION_SECONDS = 1
            self.FRAME_DURATION_SECONDS = 0.5
            self.MAX_FRAMES = 15
            self.CHARACTERS_PER_FRAME = 2

            self.set_title = set_title
            self.unread_count = unread_count
            self.sender = sender
            self.subject = subject
            self.animation_frame = 0
            self.thread = None

        def start(self):
            logger.debug(f"start animation: {self.unread_count} {self.sender} {self.subject}")
            self.thread = threading.Thread(target=self.animate)
            self.thread.start()

        @log_errors
        def animate(self):
            animation_index = 0
            reached_end = False
            while threading.current_thread() == self.thread and not reached_end and animation_index < self.MAX_FRAMES:
                logger.debug(f"animation frame: {animation_index}")
                reached_end = self.show_frame(animation_index)
                animation_index = animation_index + 1
                time.sleep(
                    self.FIRST_FRAME_DURATION_SECONDS if animation_index == 0 else self.FRAME_DURATION_SECONDS
                )
            # After the animation is finished, show beginning of the extra info
            _ = self.show_frame(0)

        def get_line_for_frame(self, animation_frame: int, text: str) -> tuple[str, bool]:
            """
            Returns the line to show for the given animation frame.
            If the end of the text is returned the second return value is True.
            """
            logger.debug(f"get_line_for_frame: {animation_frame} {text}")
            if len(text) <= EXTRA_INFO_MAX_LENGTH:
                return (text, True)

            offset = max(
                min(animation_frame * self.CHARACTERS_PER_FRAME, len(text) - EXTRA_INFO_MAX_LENGTH), 0
            )
            return (
                text[offset : offset + EXTRA_INFO_MAX_LENGTH],
                offset + EXTRA_INFO_MAX_LENGTH >= len(text),
            )

        def show_frame(self, animation_frame: int) -> bool:
            """
            Displays information for the given animation frame.
            Returns True if the animation is finished.
            """
            sender_line, sender_reached_end = self.get_line_for_frame(animation_frame, self.sender)
            subject_line, subject_reached_end = self.get_line_for_frame(animation_frame, self.subject)
            title = f"{self.unread_count}"
            if sender_line != "":
                title += f"\n{sender_line}"
            if subject_line != "":
                title += f"\n{subject_line}"

            self.set_title(title)
            return sender_reached_end and subject_reached_end

    def __init__(
        self,
        set_state_callback: callable,
        set_title_callback: callable,
        show_sender: bool,
        show_subject: bool,
    ):
        super().__init__(set_state_callback, set_title_callback, show_sender, show_subject)
        self.animation = None

    def update_tile(self, folder: win32com.client.CDispatch) -> None:
        unread_count = folder.UnReadItemCount
        if unread_count == 0:
            super().update_tile(folder)
        else:
            self.set_state(MailStates.UNREAD)
            last_unread_email = folder.Items.Restrict("[UnRead] = True").GetLast()
            # Sometimes Outlook shows an unread counter > 0, but there are no unread emails.
            # Maybe it's caused by sync errors, because the unread message appears after a few minutes.
            if not ("SenderName" in dir(last_unread_email) and "Subject" in dir(last_unread_email)):
                super().update_tile(folder)
                return
            sender = last_unread_email.SenderName
            subject = last_unread_email.Subject
            self.animation = self.TileAnimation(self.set_title, unread_count, sender, subject)
            self.animation.start()

    def get_extra_info_line(self, animation_frame: int, text: str):
        logger.debug(f"get_extra_info_line: {animation_frame} {text}")
        if len(text) <= EXTRA_INFO_MAX_LENGTH:
            return text

        offset = max(min(animation_frame * 2, len(text) - EXTRA_INFO_MAX_LENGTH), 0)
        return (
            text[offset : offset + EXTRA_INFO_MAX_LENGTH],
            offset + EXTRA_INFO_MAX_LENGTH >= len(text),
        )

    def stop(self):
        if self.animation is not None:
            self.animation.thread = None
            self.animation = None
