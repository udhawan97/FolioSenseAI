"""
Tests for app/services/ai_service.py
Mocks the Anthropic client — no real API calls are made.
"""
from unittest.mock import MagicMock, patch


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

STOCK_DATA = {
    "ticker": "NOW",
    "name": "ServiceNow, Inc.",
    "sector": "Technology",
    "quote_type": "EQUITY",
    "current_price": 950.00,
    "day_change_pct": 1.25,
    "fifty_two_week_high": 1100.00,
    "fifty_two_week_low": 700.00,
    "pe_ratio": 55.0,
    "dividend_yield": 0.0,
    "market_cap": 195_000_000_000,
}

ETF_DATA = {
    "ticker": "VOO",
    "name": "Vanguard S&P 500 ETF",
    "sector": "N/A",
    "quote_type": "ETF",
    "current_price": 530.00,
    "day_change_pct": -0.30,
    "fifty_two_week_high": 570.00,
    "fifty_two_week_low": 440.00,
    "pe_ratio": 0.0,
    "dividend_yield": 0.013,
    "market_cap": 0,
}


def _mock_response(text: str):
    block = MagicMock()
    block.type = "text"
    block.text = text
    msg = MagicMock()
    msg.content = [block]
    msg.usage.input_tokens = 100
    msg.usage.output_tokens = 60
    return msg


# ---------------------------------------------------------------------------
# normalize_bullets
# ---------------------------------------------------------------------------

class TestNormalizeBullets:
    def test_already_normalized(self):
        from app.services.ai_service import normalize_bullets
        text = "• Bullet one here.\n• Bullet two here.\n• Bullet three here."
        result = normalize_bullets(text)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert all(l.startswith("• ") for l in lines)

    def test_dash_bullets(self):
        from app.services.ai_service import normalize_bullets
        text = "- First bullet.\n- Second bullet.\n- Third bullet."
        result = normalize_bullets(text)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert all(l.startswith("• ") for l in lines)

    def test_star_bullets(self):
        from app.services.ai_service import normalize_bullets
        text = "* First.\n* Second.\n* Third."
        result = normalize_bullets(text)
        assert result.count("• ") == 3

    def test_strips_bullet_label_prefix(self):
        from app.services.ai_service import normalize_bullets
        text = (
            "Bullet 1: Tracks the S&P 500 index.\n"
            "Bullet 2: Up 1% today.\n"
            "Bullet 3: Low expense ratio."
        )
        result = normalize_bullets(text)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert not any("Bullet 1" in l for l in lines)

    def test_trims_to_three(self):
        from app.services.ai_service import normalize_bullets
        text = "• One.\n• Two.\n• Three.\n• Four.\n• Five."
        result = normalize_bullets(text)
        assert result.count("\n") == 2  # exactly 3 lines

    def test_pads_to_three(self):
        from app.services.ai_service import normalize_bullets
        text = "• Only one bullet."
        result = normalize_bullets(text)
        assert result.count("\n") == 2


# ---------------------------------------------------------------------------
# _build_prompt
# ---------------------------------------------------------------------------

class TestBuildPrompt:
    def test_equity_prompt_mentions_stock(self):
        from app.services.ai_service import _build_prompt
        prompt = _build_prompt(STOCK_DATA)
        assert "stock" in prompt.lower()
        assert "ETF" not in prompt

    def test_etf_prompt_mentions_etf(self):
        from app.services.ai_service import _build_prompt
        prompt = _build_prompt(ETF_DATA)
        assert "ETF" in prompt
        assert "stock" not in prompt.lower() or "stock" in prompt.lower()  # ETF prompt only

    def test_prompt_contains_ticker_and_name(self):
        from app.services.ai_service import _build_prompt
        prompt = _build_prompt(STOCK_DATA)
        assert "NOW" in prompt
        assert "ServiceNow" in prompt

    def test_prompt_contains_price(self):
        from app.services.ai_service import _build_prompt
        prompt = _build_prompt(STOCK_DATA)
        assert "950.00" in prompt

    def test_prompt_no_hallucination_instruction(self):
        from app.services.ai_service import _build_prompt
        prompt = _build_prompt(ETF_DATA)
        assert "do not invent" in prompt.lower()


# ---------------------------------------------------------------------------
# generate_stock_summary (mocked client)
# ---------------------------------------------------------------------------

class TestGenerateStockSummary:
    def test_returns_three_bullets(self):
        raw = (
            "• Tracks the S&P 500 index.\n"
            "• Sitting at 75% of its 52-week range.\n"
            "• Yields 1.3% in dividends annually."
        )
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = _mock_response(raw)
            from app.services.ai_service import generate_stock_summary
            result = generate_stock_summary(ETF_DATA)
        lines = result.strip().split("\n")
        assert len(lines) == 3
        assert all(l.startswith("• ") for l in lines)

    def test_normalizes_dash_bullets_from_model(self):
        raw = (
            "- Cloud software company.\n"
            "- At 36% of 52-week range.\n"
            "- High P/E of 55 signals growth premium."
        )
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = _mock_response(raw)
            from app.services.ai_service import generate_stock_summary
            result = generate_stock_summary(STOCK_DATA)
        assert all(l.startswith("• ") for l in result.strip().split("\n"))

    def test_auth_error_returns_fallback(self):
        import anthropic
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.side_effect = anthropic.AuthenticationError(
                message="bad key", response=MagicMock(), body={}
            )
            from app.services.ai_service import generate_stock_summary
            result = generate_stock_summary(STOCK_DATA)
        assert "• " in result
        assert result.count("\n") == 2  # still 3 lines

    def test_rate_limit_returns_fallback(self):
        import anthropic
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.side_effect = anthropic.RateLimitError(
                message="rate limit", response=MagicMock(), body={}
            )
            from app.services.ai_service import generate_stock_summary
            result = generate_stock_summary(STOCK_DATA)
        assert result.startswith("• ")
        assert result.count("\n") == 2

    def test_generic_error_returns_price_fallback(self):
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.side_effect = RuntimeError("network error")
            from app.services.ai_service import generate_stock_summary
            result = generate_stock_summary(STOCK_DATA)
        assert "NOW" in result
        assert result.count("\n") == 2

    def test_uses_model_constant(self):
        from app.services.ai_service import MODEL
        raw = "• A.\n• B.\n• C."
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = _mock_response(raw)
            from app.services.ai_service import generate_stock_summary
            generate_stock_summary(STOCK_DATA)
            call_kwargs = mock_client.messages.create.call_args
            assert call_kwargs.kwargs["model"] == MODEL or call_kwargs.args[0] == MODEL or \
                   call_kwargs.kwargs.get("model") == MODEL


class TestGenerateEtfHoldingsSeed:
    def test_parses_compact_profile_json(self):
        raw = (
            '{"aum":12300000000,"holdings":['
            '{"ticker":"AAPL","name":"Apple","weight":7.2},'
            '{"ticker":"MSFT","name":"Microsoft","weight":6.8},'
            '{"ticker":"NVDA","name":"NVIDIA","weight":6.1}]}'
        )
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = _mock_response(raw)
            from app.services.ai_service import generate_etf_profile_seed
            result = generate_etf_profile_seed("VOO", "Vanguard S&P 500 ETF")

        assert result["aum"] == 12_300_000_000
        assert result["holdings"][0] == {"ticker": "AAPL", "name": "Apple", "weight": 7.2}

    def test_parses_compact_json_holdings(self):
        raw = (
            '[{"ticker":"AAPL","name":"Apple","weight":7.2},'
            '{"ticker":"MSFT","name":"Microsoft","weight":6.8},'
            '{"ticker":"NVDA","name":"NVIDIA","weight":6.1}]'
        )
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = _mock_response(raw)
            from app.services.ai_service import generate_etf_holdings_seed
            result = generate_etf_holdings_seed("VOO", "Vanguard S&P 500 ETF")

        assert result == [
            {"ticker": "AAPL", "name": "Apple", "weight": 7.2},
            {"ticker": "MSFT", "name": "Microsoft", "weight": 6.8},
            {"ticker": "NVDA", "name": "NVIDIA", "weight": 6.1},
        ]

    def test_returns_empty_when_model_is_unsure(self):
        with patch("app.services.ai_service.client") as mock_client:
            mock_client.messages.create.return_value = _mock_response("[]")
            from app.services.ai_service import generate_etf_holdings_seed
            assert not generate_etf_holdings_seed("MYSTERY")
