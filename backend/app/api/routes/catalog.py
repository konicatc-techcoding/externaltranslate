from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, status

from backend.app.api.dependencies import (
    DeviceLister,
    LoopbackLister,
    PrerequisiteReporter,
    get_device_lister,
    get_loopback_lister,
    get_prerequisite_reporter,
)
from backend.app.api.models import (
    DeviceItem,
    DeviceResponse,
    LoopbackEndpointItem,
    LoopbackEndpointResponse,
    PrerequisiteItem,
    PrerequisiteResponse,
)
from backend.app.audio.devices import AudioDeviceError
from backend.app.audio.sources.wasapi_loopback import LoopbackDeviceError

router = APIRouter(prefix="/api", tags=["catalog"])


@router.get("/prerequisites", response_model=PrerequisiteResponse)
def read_prerequisites(
    reporter: Annotated[PrerequisiteReporter, Depends(get_prerequisite_reporter)],
) -> PrerequisiteResponse:
    results = [PrerequisiteItem(**result.to_dict()) for result in reporter()]
    return PrerequisiteResponse(results=results)


@router.get("/devices", response_model=DeviceResponse)
def read_devices(
    lister: Annotated[DeviceLister, Depends(get_device_lister)],
) -> DeviceResponse:
    try:
        devices = lister()
    except AudioDeviceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return DeviceResponse(
        devices=[
            DeviceItem(
                index=device.index,
                name=device.name,
                host_api=device.host_api,
                max_input_channels=device.max_input_channels,
                default_sample_rate=device.default_sample_rate,
            )
            for device in devices
        ]
    )


@router.get("/loopback-endpoints", response_model=LoopbackEndpointResponse)
def read_loopback_endpoints(
    lister: Annotated[LoopbackLister, Depends(get_loopback_lister)],
) -> LoopbackEndpointResponse:
    try:
        endpoints = lister()
    except LoopbackDeviceError as exc:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE, detail=str(exc)
        ) from None
    return LoopbackEndpointResponse(
        endpoints=[
            LoopbackEndpointItem(
                index=endpoint.index,
                name=endpoint.name,
                host_api=endpoint.host_api,
                channels=endpoint.channels,
                default_sample_rate=endpoint.default_sample_rate,
                is_default=endpoint.is_default,
            )
            for endpoint in endpoints
        ]
    )
