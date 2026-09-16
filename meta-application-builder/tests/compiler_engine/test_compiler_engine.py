import pytest
from compiler_engine.brain_adapter.ir_sanitizer import (
    IRSanitizationError,
    IRSanitizer,
    UntrustedIRField,
    UntrustedIRModel,
)
from compiler_engine.meta_compiler.pydantic_emitter import PydanticEmitter
from compiler_engine.verification.temporal_validator import (
    NonDeterministicPatternError,
    TemporalValidator,
)


def test_ir_sanitizer_valid():
    payload = {
        "model_name": "UserSpec",
        "fields": [{"name": "username", "type_hint": "str", "nullable": False}]
    }
    model = IRSanitizer.sanitize(payload)
    assert model.model_name == "UserSpec"

def test_ir_sanitizer_injection_fails():
    payload = {
        "model_name": "__globals__",
        "fields": []
    }
    with pytest.raises(IRSanitizationError):
        IRSanitizer.sanitize(payload)

def test_pydantic_emitter():
    ir = UntrustedIRModel(
        model_name="ItemSpec",
        fields=[UntrustedIRField(name="price", type_hint="float", nullable=False)]
    )
    code = PydanticEmitter.emit_model_code(ir)
    assert "class ItemSpec(BaseModel):" in code
    assert "price: float" in code

def test_temporal_validator_violation():
    code = "import random\n\nx = random.randint(1, 10)"
    with pytest.raises(NonDeterministicPatternError):
        TemporalValidator.validate_code_string(code)