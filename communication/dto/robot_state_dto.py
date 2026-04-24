from dataclasses import dataclass


@dataclass
class RobotStateDto:
    pos: list
    ve_pelota: bool

    @staticmethod
    def from_dict(data: dict) -> "RobotStateDto":
        return RobotStateDto(
            pos=data["pos"],
            ve_pelota=data["ve_pelota"]
        )
