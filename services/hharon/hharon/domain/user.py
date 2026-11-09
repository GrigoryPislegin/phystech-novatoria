from typing import ClassVar

import pydantic


class HharonUser(pydantic.BaseModel):
    model_config: ClassVar[pydantic.ConfigDict] = pydantic.ConfigDict(frozen=True)

    user_id: str
    hh_manager_id: str
    hh_employer_id: str
    name: str
    email: str
