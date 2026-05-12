from dataclasses import dataclass


@dataclass
class RolesDto:
    robot1: str
    robot2: str

    def to_dict(self) -> dict:
        return {"robot1": self.robot1, "robot2": self.robot2}
