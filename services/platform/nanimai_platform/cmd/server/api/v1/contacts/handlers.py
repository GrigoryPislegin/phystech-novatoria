from dishka.integrations.fastapi import FromDishka, inject
from fastapi import APIRouter, HTTPException, status

from nanimai_platform.services.customer_contacts import (
    CustomerContactServiceCreateError,
    CustomerContactServiceError,
    CustomerContactServiceInvalidDataError,
)
from nanimai_platform.services.customer_contacts.service import CustomerContactService

from .dto import CreateCustomerContactRequest, CreateCustomerContactResponse

router = APIRouter(tags=["contacts"])


@router.post("")
@inject
async def post_customer_contact(
    request_body: CreateCustomerContactRequest,
    contact_service: FromDishka[CustomerContactService],
) -> CreateCustomerContactResponse:
    try:
        contact = await contact_service.create(
            CustomerContactService.CreateCustomerContactRequest(
                name=request_body.name,
                contact=request_body.contact,
                number_employees=0,
            )
        )
        return CreateCustomerContactResponse(id=str(contact.id))
    except CustomerContactServiceInvalidDataError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="Invalid data in request",
        ) from e
    except CustomerContactServiceCreateError as e:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="failed to create customer contact",
        ) from e
    except CustomerContactServiceError as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="internal server error",
        ) from e
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="failed to create customer contact",
        ) from e
