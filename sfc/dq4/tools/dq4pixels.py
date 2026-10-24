"""Assemble the original DQ4 sprite and terrain masters; sfc/dq4/docs/dq4-graphics.md."""

from dq4sprites import build_sprites
from dq4terrain import build_terrain


def build_assets():
    return build_sprites() | build_terrain()
