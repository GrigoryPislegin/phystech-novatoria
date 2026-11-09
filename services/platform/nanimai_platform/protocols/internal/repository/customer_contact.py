from abc import ABC, abstractmethod
from dataclasses import dataclass

from nanimai_platform.domain import CustomerContact, CustomerContactID


class CustomerContactRepositoryError(Exception): ...


class CustomerContactValidateError(CustomerContactRepositoryError): ...


class CustomerContactNotFoundError(CustomerContactRepositoryError): ...


class CreateCustomerContactError(CustomerContactRepositoryError): ...


class ReadCustomerContactError(CustomerContactRepositoryError): ...


class UpdateCustomerContactError(CustomerContactRepositoryError): ...


class DeleteCustomerContactError(CustomerContactRepositoryError): ...


class CustomerContactRepositoryProtocol(ABC):
    @dataclass
    class CreateCustomerContactRequest:
        name: str
        contact: str
        number_employees: int

    @abstractmethod
    async def create_customer_contact(self, request: CreateCustomerContactRequest) -> CustomerContact:
        """creates contact in repository

        Raises:
            CreateCustomerContactError - not expected exception
            CustomerContactValidateError - validation error
        Returns:
            CustomerContact - created contact
        """
        ...

    @dataclass
    class ReadCustomerContactRequest:
        id: CustomerContactID

    @abstractmethod
    async def read_customer_contact(self, request: ReadCustomerContactRequest) -> CustomerContact:
        """reads contact in repository

        Raises:
            ReadCustomerContactError - not expected exception
            CustomerContactValidateError - validation error
            CustomerContactNotFoundError - customer not found
        Returns:
            CustomerContact - read contact
        """
        ...

    @dataclass
    class UpdateCustomerContactRequest:
        id: CustomerContactID

        name: str | None = None
        contact: str | None = None
        number_employees: int | None = None

    @abstractmethod
    async def update_customer_contact(self, request: UpdateCustomerContactRequest) -> CustomerContact:
        """updates contact in repository

        Raises:
            UpdateCustomerContactError - not expected exception
            CustomerContactValidateError - validation error
            CustomerContactNotFoundError - customer not found
        Returns:
            CustomerContact - updated contact
        """
        ...

    @dataclass
    class DeleteCustomerContactRequest:
        id: CustomerContactID

    @abstractmethod
    async def delete_customer_contact(self, request: DeleteCustomerContactRequest) -> CustomerContact:
        """deletes customer contact in repository

        Raises:
            DeleteCustomerContactError - not expected exception
            CustomerContactValidateError - validation error
            CustomerContactNotFoundError - customer not found
        Returns:
            CustomerContact - deleted contact
        """
        ...

    @dataclass
    class ReadManyCustomerContactsRequest:
        customer_contact_ids: list[CustomerContactID]

    @abstractmethod
    async def read_many_customer_contacts(
        self, request: ReadManyCustomerContactsRequest
    ) -> list[CustomerContact | None]:
        """reads many contacts in repository

        Raises:
            ReadCustomerContactError - not expected exception
            CustomerContactValidateError - validation error
            CustomerContactNotFoundError - customer not found
        Returns:
            list[CustomerContact | None] - list of contacts or None if contact does not exist
        """
        ...
