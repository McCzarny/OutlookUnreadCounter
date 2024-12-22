from pathlib import Path

from streamdeck_sdk_pi import *

OUTPUT_DIR = Path(__file__).parent
TEMPLATE = Path(__file__).parent / "pi_template.html"


def main():
    pi = PropertyInspector(
        action_uuid="com.mcczarny.outlookunreadcounter.unreadcounter",
        elements=[
            Select(
                uid="account",
                label="Outlook Account",
                values=[""],
                default_value="",
            ),
            Select(
                    uid="extra_info",
                    label="Include Extra Info",
                    values=["None", "Subject", "Sender", "Both"],
                    default_value="None",
            ),
            Checkbox(
                label="Animate Extra Info",
                items=[
                    CheckboxItem(
                        uid="animate_extra_info",
                        label="on",
                        checked=False,
                    ),
                ],
            ),
        ]
    )
    pi.build(output_dir=OUTPUT_DIR, template=TEMPLATE)


if __name__ == '__main__':
    # Run to generate Property Inspector
    main()
