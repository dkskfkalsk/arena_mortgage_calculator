import importlib.util
from pathlib import Path
import unittest


helper_path = Path(__file__).resolve().parents[1] / "g2b-order-plan-search" / "scripts" / "g2b_order_plan.py"
spec = importlib.util.spec_from_file_location("g2b_order_plan_helper", helper_path)
assert spec is not None
assert spec.loader is not None
g2b_order_plan = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g2b_order_plan)

build_parser = g2b_order_plan.build_parser
build_query = g2b_order_plan.build_query
resolve_proxy_base_url = g2b_order_plan.resolve_proxy_base_url
search_order_plans = g2b_order_plan.search_order_plans


class G2bOrderPlanHelperTest(unittest.TestCase):
    def test_build_query_normalizes_month_dates_and_optional_filters(self):
        args = build_parser().parse_args([
            "--kind", "용역",
            "--keyword", "청소",
            "--order-from", "2025-01",
            "--order-to", "2025.03",
            "--posted-from", "2025-01-01",
            "--posted-to", "202501312359",
            "--institution", "조달청",
            "--page", "2",
            "--limit", "20",
        ])
        self.assertEqual(build_query(args), {
            "kind": "용역",
            "page": "2",
            "limit": "20",
            "keyword": "청소",
            "orderFrom": "202501",
            "orderTo": "202503",
            "postedFrom": "20250101",
            "postedTo": "202501312359",
            "institution": "조달청",
        })

    def test_search_order_plans_calls_proxy_route_with_query(self):
        captured = {}

        def fake_read_json(request):
            captured["url"] = request.full_url
            captured["method"] = request.get_method()
            captured["headers"] = request.headers
            return {"items": [{"bizNm": "청소 용역"}]}

        payload = search_order_plans(
            {"kind": "service", "keyword": "청소"},
            base_url="https://proxy.example.com/",
            read_json=fake_read_json,
        )

        self.assertEqual(payload["items"][0]["bizNm"], "청소 용역")
        self.assertEqual(captured["method"], "GET")
        self.assertTrue(captured["url"].startswith("https://proxy.example.com/v1/g2b/order-plans?"))
        self.assertIn("k-skill-g2b-order-plan-search", captured["headers"]["User-agent"])
        self.assertIn("kind=service", captured["url"])
        self.assertIn("keyword=%EC%B2%AD%EC%86%8C", captured["url"])

    def test_resolve_proxy_base_url_defaults_to_hosted_proxy(self):
        self.assertEqual(resolve_proxy_base_url(None, env={}), "https://k-skill-proxy.nomadamas.org")
        self.assertEqual(resolve_proxy_base_url(None, env={"KSKILL_PROXY_BASE_URL": "https://proxy.example.com/"}), "https://proxy.example.com")
        with self.assertRaisesRegex(ValueError, "KSKILL_PROXY_BASE_URL"):
            resolve_proxy_base_url(None, env={"KSKILL_PROXY_BASE_URL": "off"})


if __name__ == "__main__":
    unittest.main()
