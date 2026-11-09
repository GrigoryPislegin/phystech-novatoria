from typing import final

import structlog
from pydantic import BaseModel

from nanimai_platform.domain.customer.contact import CustomerContact
from nanimai_platform.domain.scalar.scalars import CustomerContactID
from nanimai_platform.protocols.external.notification.protocol import NotificationError, NotificationProtocol
from nanimai_platform.protocols.internal.repository.customer_contact import (
    CustomerContactNotFoundError,
    CustomerContactRepositoryError,
    CustomerContactRepositoryProtocol,
    CustomerContactValidateError,
)
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.services.CustomerContactService")


class CustomerContactServiceError(Exception): ...


class CustomerContactServiceCustomerContactNotFoundError(CustomerContactServiceError): ...


class CustomerContactServiceInvalidDataError(CustomerContactServiceError): ...


class CustomerContactServiceCreateError(CustomerContactServiceError): ...


class CustomerContactServiceUpdateError(CustomerContactServiceError): ...


class CustomerContactServiceDeleteError(CustomerContactServiceError): ...


class CustomerContactServiceReadError(CustomerContactServiceError): ...


@final
class CustomerContactService:
    def __init__(
        self,
        customer_contact_repo: CustomerContactRepositoryProtocol,
        notification_adapter: NotificationProtocol,
    ):
        self._repo = customer_contact_repo
        self.notifications = notification_adapter

    def __notification_message(self, contact: CustomerContact) -> str:
        return f"""
            | Новый запрос на демо доступ:
            | {contact.created_at.strftime("%d.%m.%Y %H:%M")}
            | ___
            | Имя: {contact.name}
            | Контакт: {contact.contact}
            | Количество сотрудников: {contact.number_employees}
        """.removesuffix("\n").replace("            | ", "")

    class CreateCustomerContactRequest(BaseModel):
        name: str
        contact: str
        number_employees: int = 0

    @span(op="customer_contact_service", name="create_customer_contact")
    async def create(self, request: CreateCustomerContactRequest) -> CustomerContact:
        try:
            data = await self._repo.create_customer_contact(
                CustomerContactRepositoryProtocol.CreateCustomerContactRequest(
                    name=request.name,
                    contact=request.contact,
                    number_employees=request.number_employees,
                )
            )
        except CustomerContactValidateError as e:
            log.error("failed to validate customer contact", err=e)
            raise CustomerContactServiceInvalidDataError("failed to validate customer contact") from e
        except CustomerContactRepositoryError as e:
            log.error("failed to create customer contact", err=e)
            raise CustomerContactServiceCreateError("failed to create customer contact") from e

        try:
            await self.notifications.push(self.__notification_message(data))
            return data
        except NotificationError as e:
            log.error("failed to send notification", err=e)
            try:
                await self.notifications.push(self.__notification_message(data))
            except Exception as e:
                log.error("failed to send notification again", err=e)
                raise CustomerContactServiceError("failed to create customer contact") from e
            else:
                return data
        except Exception as e:
            log.error("failed to create customer contact", err=e)
            raise CustomerContactServiceError("failed to create customer contact") from e

    class ReadCustomerContactRequest(BaseModel):
        id: CustomerContactID

    @span(op="customer_contact_service", name="read_customer_contact")
    async def read(self, request: ReadCustomerContactRequest) -> CustomerContact:
        try:
            return await self._repo.read_customer_contact(
                CustomerContactRepositoryProtocol.ReadCustomerContactRequest(id=request.id)
            )
        except CustomerContactNotFoundError as e:
            log.error("failed to find customer contact", err=e)
            raise CustomerContactServiceReadError("failed to find customer contact") from e
        except CustomerContactRepositoryError as e:
            log.error("failed to read customer contact", err=e)
            raise CustomerContactServiceReadError("failed to read customer contact") from e
        except Exception as e:
            log.error("failed to read customer with unexpected error", err=e)
            raise e

    class ReadManyCustomerContactsRequest(BaseModel):
        customer_contact_ids: list[CustomerContactID]

    @span(op="customer_contact_service", name="read_many_customer_contacts")
    async def read_many(self, request: ReadManyCustomerContactsRequest) -> list[CustomerContact | None]:
        try:
            return await self._repo.read_many_customer_contacts(
                CustomerContactRepositoryProtocol.ReadManyCustomerContactsRequest(
                    customer_contact_ids=request.customer_contact_ids
                )
            )
        except CustomerContactRepositoryError as e:
            log.error("failed to read many customers contacts", err=e)
            raise CustomerContactServiceReadError("failed to read customers contacts") from e
        except Exception as e:
            log.error("failed to read many customers contacts", err=e)
            raise CustomerContactServiceError("failed to read customers contacts") from e

    class UpdateCustomerContactRequest(BaseModel):
        id: CustomerContactID
        name: str | None = None
        contact: str | None = None
        number_employees: int | None = None

    @span(op="customer_contact_service", name="update_customer_contact")
    async def update(self, request: UpdateCustomerContactRequest) -> CustomerContact:
        try:
            return await self._repo.update_customer_contact(
                CustomerContactRepositoryProtocol.UpdateCustomerContactRequest(
                    id=request.id,
                    name=request.name,
                    contact=request.contact,
                    number_employees=request.number_employees,
                )
            )
        except CustomerContactNotFoundError as e:
            log.error("failed to read customer contact", err=e)
            raise CustomerContactServiceReadError("failed to find customer contact") from e
        except CustomerContactRepositoryError as e:
            log.error("failed to update customer contacts", err=e)
            raise CustomerContactServiceUpdateError("failed to update customer contact") from e
        except Exception as e:
            log.error("failed to update customer contacts")
            raise CustomerContactServiceUpdateError("failed to update customer contact") from e

    class DeleteCustomerContactReqeust(BaseModel):
        id: CustomerContactID

    @span(op="customer_contact_service", name="delete_customer_contact")
    async def delete(self, customer_contact: DeleteCustomerContactReqeust) -> CustomerContact:
        try:
            return await self._repo.delete_customer_contact(
                CustomerContactRepositoryProtocol.DeleteCustomerContactRequest(id=customer_contact.id)
            )
        except CustomerContactNotFoundError as e:
            log.error("failed to read customer contact", err=e)
            raise CustomerContactServiceReadError("failed to find customer contact") from e
        except CustomerContactRepositoryError as e:
            log.error("failed to delete customer contact", err=e)
            raise CustomerContactServiceDeleteError("failed to delete customer contact") from e
        except Exception as e:
            log.error("failed to delete customer contact")
            raise CustomerContactServiceDeleteError("failed to delete customer contact") from e
