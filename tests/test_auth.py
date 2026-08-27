from resources.lib import auth


def test_extract_token_variants():
    assert auth._extract_token({"data": {"access_token": "abc"}}) == "abc"
    assert auth._extract_token({"data": {"token": "t"}}) == "t"
    assert auth._extract_token({"data": {"auth_token": "at"}}) == "at"
    assert auth._extract_token({"data": {"api_key": "k"}}) == "k"
    assert auth._extract_token({"data": "rawstring"}) == "rawstring"
    assert auth._extract_token({}) == ""
    assert auth._extract_token({"data": {}}) == ""
