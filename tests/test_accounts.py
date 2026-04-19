from kis_mcp_server.accounts import (
    extract_total_eval_amt,
    infer_account_type,
    is_irp_account,
    to_int,
)


def test_is_irp_account_only_product_code_29():
    assert is_irp_account("29") is True
    assert is_irp_account("22") is False
    assert is_irp_account("01") is False


def test_infer_account_type_prefers_known_cano():
    assert infer_account_type("44299692", "01") == "ria"
    assert infer_account_type("43786274", "01") == "isa"
    assert infer_account_type("43362670", "01") == "irp"


def test_infer_account_type_falls_back_to_product_code():
    assert infer_account_type("00000000", "01") == "brokerage"
    assert infer_account_type("00000000", "22") == "pension"
    assert infer_account_type("00000000", "29") == "irp"
    assert infer_account_type("00000000", "99") == "unknown"


def test_to_int_parses_kis_numeric_strings():
    assert to_int("1,234") == 1234
    assert to_int("1234.0") == 1234
    assert to_int("") is None
    assert to_int(None) is None
    assert to_int("not-a-number") is None


def test_extract_total_eval_amt_known_fields_in_priority_order():
    assert extract_total_eval_amt({"output2": {"tot_evlu_amt": "1,000"}}) == 1000
    assert extract_total_eval_amt({"output2": {"scts_evlu_amt": "2,000"}}) == 2000
    assert extract_total_eval_amt({"output2": {"tot_asst_amt": "3,000"}}) == 3000
    assert extract_total_eval_amt({"output2": {"dnca_tota": "4,000"}}) == 4000


def test_extract_total_eval_amt_ignores_unexpected_shapes():
    assert extract_total_eval_amt({"output2": []}) is None
    assert extract_total_eval_amt({}) is None
