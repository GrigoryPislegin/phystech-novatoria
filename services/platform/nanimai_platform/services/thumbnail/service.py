# pyright: reportUnknownArgumentType=false, reportUnknownMemberType=false, reportUnknownVariableType=false, reportUnknownParameterType=false
import hashlib as hl
import io
import random
from typing import final

import cv2 as cv
import numpy as np
import structlog
from PIL import Image

from nanimai_platform.protocols.internal.cache.protocol import CacheProtocol
from nanimai_platform.protocols.internal.file_storage.protocol import FileStorageProtocol
from nanimai_platform.utils.logging_span import span

log = structlog.stdlib.get_logger("app.service.ThumbnailService")


DEFAULT_MAIN_COLOR = "4D61F4"


class ThumbnailServiceError(Exception): ...


@final
class ThumbnailService:
    def __init__(self, public_storage: FileStorageProtocol, cache: CacheProtocol):
        self._file_storage_adapter = public_storage
        self._cache = cache
        self._generator = IdenticonGenerator()

    @span(op="thumbnail_service", name="create_candidate_thumbnail")
    async def create_candidate_thumbnail(self, name: str, main_color: str | None = None) -> str:
        color = main_color or DEFAULT_MAIN_COLOR
        if (path := await self._cache.get(self._generate_key(name, color))) is not None:
            return path

        return await self._generate(name, color)

    @span(op="thumbnail_service", name="create_analysis_thumbnail")
    async def create_vacancy_thumbnail(self, name: str, main_color: str | None = None) -> str:
        color = main_color or DEFAULT_MAIN_COLOR
        if (path := await self._cache.get(self._generate_key(name, color))) is not None:
            return path

        return await self._generate(name, color)

    @span(op="thumbnail_service", name="create_user_profile_thumbnail")
    async def create_user_profile_thumbnail(self, name: str, main_color: str | None = None) -> str:
        color = main_color or DEFAULT_MAIN_COLOR
        if (path := await self._cache.get(self._generate_key(name, color))) is not None:
            return path

        return await self._generate(name, color)

    @span(op="thumbnail_service", name="create_project_thumbnail")
    async def create_project_thumbnail(self, name: str, main_color: str | None = None) -> str:
        color = main_color or DEFAULT_MAIN_COLOR
        if (path := await self._cache.get(self._generate_key(name, color))) is not None:
            return path

        return await self._generate(name, color)

    @span(op="thumbnail_service", name="generate_key")
    def _generate_key(self, value: str, main_color: str) -> str:
        return hl.sha256(f"{value}:{main_color}".encode()).hexdigest()

    @span(op="thumbnail_service", name="generate")
    async def _generate(self, value: str, main_color: str) -> str:
        try:
            key = self._generate_key(value, main_color)
            path = f"thumb/{key}.webp"

            log.info("generated thumbnail path", value=value, main_color=main_color, path=path)
            buffer = io.BytesIO()

            log.info("generating thumbnail", value=value, main_color=main_color)
            image = self._generator.generate(value, main_color)
            Image.fromarray(image).save(buffer, format="WEBP")  # type: ignore
            log.info(
                "thumbnail generated successfully", value=value, main_color=main_color, n_bytes=len(buffer.getvalue())
            )
            await self._file_storage_adapter.upload(path, buffer.getvalue())
            await self._cache.set(key, path)

            return path
        except Exception as e:
            raise ThumbnailServiceError("failed to create thumbnail") from e


@final
class IdenticonGenerator:
    DEFAULT_WIDTH = 256

    @span(op="identicon_generator", name="generate_identicon")
    def generate(self, hash_string: str, main_color_hex: str = DEFAULT_MAIN_COLOR) -> np.ndarray:
        seed = int(hl.sha256(hash_string.encode()).hexdigest(), 16) % 2**32
        rng = random.Random(seed)
        np_rng = np.random.default_rng(seed)

        color = main_color_hex.lstrip("#")
        r = int(color[0:2], 16)
        g = int(color[2:4], 16)
        b = int(color[4:6], 16)

        rgb_color = np.array([[[r, g, b]]], dtype=np.uint8)
        hsv_color = cv.cvtColor(rgb_color, cv.COLOR_RGB2HSV)[0][0]

        hue, sat, val = hsv_color

        colors = self._generate_color_variations(hue, sat, val, rng, np_rng)

        hsvimg = self.__create_horizontal_symmetric_img(self.DEFAULT_WIDTH, colors, np_rng)
        return cv.cvtColor(hsvimg, cv.COLOR_HSV2RGB)

    @staticmethod
    def _generate_color_variations(
        hue: int, sat: int, val: int, rng: random.Random, np_rng: np.random.Generator
    ) -> list[tuple[int, int, int]]:
        colors = []
        for _ in range(5):
            new_sat = max(min(int(np_rng.normal(sat, 100)), 255), 150)
            new_val = max(min(int(np_rng.normal(val, 100)), 255), 180)
            new_hue = (rng.randint(-3, 3) + int(hue)) % 255
            if rng.random() < 0.35:
                new_hue = hue
            colors.append((new_hue, new_sat, new_val))
        return colors

    @staticmethod
    def __scale_img_to_multiple(img: np.ndarray, scaled_width: int) -> np.ndarray:
        if img.shape[0] != scaled_width:
            multiple_factor = int(scaled_width / img.shape[0])
            height, width, channels = img.shape
            scaled_img = np.zeros((scaled_width, scaled_width, channels), np.uint8)

            for src_row in range(height):
                for src_col in range(width):
                    src_color = img[src_row, src_col]
                    for scaled_row in range(src_row * multiple_factor, (src_row + 1) * multiple_factor):
                        for scaled_col in range(src_col * multiple_factor, (src_col + 1) * multiple_factor):
                            scaled_img[scaled_row, scaled_col] = src_color
            return scaled_img
        return img.copy()

    @staticmethod
    def __create_horizontal_symmetric_img(
        width: int, colors: list[tuple[int, int, int]], np_rng: np.random.Generator
    ) -> np.ndarray:
        base_width = 16
        base_shape = (base_width, base_width, 3)
        base_img = np.zeros(base_shape, np.uint8)

        for row in range(base_width):
            for col in range(base_width // 2):
                chosen_color = colors[int(np_rng.integers(len(colors)))]
                base_img[row, col] = chosen_color
                base_img[row, base_width - col - 1] = chosen_color

        return IdenticonGenerator.__scale_img_to_multiple(base_img, width)
