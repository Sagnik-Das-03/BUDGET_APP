"""Makes app/schemas.py and app/config.py agnostic to whether Pydantic v1 or
v2 is installed, so the SAME source tree runs on desktop/Docker (real
pydantic==2.x, pinned in requirements.txt) and on Android via Chaquopy (real
pydantic<2, pinned in the Android build's own dependency list). v2 depends
on pydantic-core (a Rust extension with no Android wheel and no Rust
toolchain in Chaquopy to build one), so Android genuinely cannot install v2
at all - this is NOT the pydantic.v1 compatibility shim bundled inside the
real v2 package, which still requires v2 (and therefore pydantic-core) to be
installed. This module picks between the two real, separate packages.

Deliberately avoids metaclass tricks - Pydantic's own BaseModel already uses
a custom metaclass in both versions, and a second one here would conflict
with it. `FromAttributes` below is instead a real (thin) BaseModel subclass,
not a plain mixin: v1's metaclass only inherits `Config` from bases that are
themselves BaseModel subclasses (checked via `issubclass(base, BaseModel)`),
silently ignoring a `Config` nested inside a non-BaseModel mixin class - a
plain-mixin version of this passed every unit test (none of them actually
serialize a schema through FastAPI) but produced a real 500 on every ORM-
backed GET endpoint the first time it was hit over real HTTP.
"""
import pydantic
from pydantic import BaseModel, Field

PYDANTIC_V2 = pydantic.VERSION.startswith("2.")


def list_field(*, min_len: int | None = None, max_len: int | None = None, **kwargs):
    """A Field() for a `list[...]`-typed attribute with a length constraint -
    v2 spells this min_length/max_length (same names it uses for strings),
    v1 spells it min_items/max_items and raises ValueError at class-
    definition time if you pass it min_length/max_length on a non-str field."""
    if PYDANTIC_V2:
        return Field(min_length=min_len, max_length=max_len, **kwargs)
    return Field(min_items=min_len, max_items=max_len, **kwargs)

if PYDANTIC_V2:
    from pydantic import field_validator as field_validator  # noqa: F401
    from pydantic_settings import BaseSettings as BaseSettings  # noqa: F401
    from pydantic_settings import SettingsConfigDict as SettingsConfigDict  # noqa: F401

    class FromAttributes(BaseModel):
        """Base for schemas built `from_attributes` (i.e. from an ORM
        object) - `class Out(FromAttributes): ...`."""
        model_config = {"from_attributes": True}

    def model_to_dict(model, **kwargs) -> dict:
        return model.model_dump(**kwargs)

else:
    from pydantic import validator as _validator
    from pydantic import BaseSettings as BaseSettings  # noqa: F401
    SettingsConfigDict = None  # unused on this branch - see config.py

    def field_validator(*fields, **kwargs):
        # v1's validator() doesn't accept v2's mode=/check_fields= kwargs -
        # every call site in this codebase only uses the plain form, so drop
        # anything v1 doesn't understand rather than mirroring v2's full API.
        kwargs.pop("mode", None)
        kwargs.pop("check_fields", None)
        return _validator(*fields, **kwargs)

    class FromAttributes(BaseModel):
        class Config:
            orm_mode = True

    def model_to_dict(model, **kwargs) -> dict:
        # v1's .dict() doesn't accept mode="json" - the one caller that
        # wants JSON-safe values converts that field itself instead.
        kwargs.pop("mode", None)
        return model.dict(**kwargs)
