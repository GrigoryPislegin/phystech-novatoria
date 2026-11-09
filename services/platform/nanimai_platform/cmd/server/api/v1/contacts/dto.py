from nanimai_platform.cmd.server.utils.dtobase import DTOBase


class CreateCustomerContactRequest(DTOBase):
    name: str
    contact: str


class CreateCustomerContactResponse(DTOBase):
    id: str
