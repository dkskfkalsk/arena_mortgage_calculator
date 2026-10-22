import importlib.util
import pathlib
import unittest
from unittest import mock


MODULE_PATH = pathlib.Path(__file__).resolve().parents[1] / "naver-blog-research" / "scripts" / "naver_search.py"
MODULE_SPEC = importlib.util.spec_from_file_location("naver_search", MODULE_PATH)
naver_search = importlib.util.module_from_spec(MODULE_SPEC)
assert MODULE_SPEC.loader is not None
MODULE_SPEC.loader.exec_module(naver_search)


def make_result(index: int) -> dict[str, str]:
    return {
        "url": f"https://blog.naver.com/author{index}/{200000000000 + index}",
        "mobile_url": f"https://m.blog.naver.com/author{index}/{200000000000 + index}",
        "author": f"author{index}",
        "title": f"title-{index}",
        "snippet": f"snippet-{index}",
    }


class RequestBuilderTest(unittest.TestCase):
    def test_build_search_params_target_blog_tab_and_switch_sm_for_paging(self):
        page_one = naver_search.build_search_params("서울 맛집", start=1, sort="sim")
        page_two = naver_search.build_search_params("서울 맛집", start=16, sort="date")

        self.assertEqual(page_one["ssc"], "tab.blog.all")
        self.assertEqual(page_one["sm"], "tab_jum")
        self.assertEqual(page_one["start"], "1")
        self.assertEqual(page_one["nso"], "so:r,p:all,a:all")

        self.assertEqual(page_two["ssc"], "tab.blog.all")
        self.assertEqual(page_two["sm"], "tab_pge")
        self.assertEqual(page_two["start"], "16")
        self.assertEqual(page_two["nso"], "so:dd,p:all,a:all")


def make_anchor(user_id: str, post_id: str, inner_html: str) -> str:
    return f'<a href="https://blog.naver.com/{user_id}/{post_id}" class="link">{inner_html}</a>'


NEW_WINDOW_LABEL_SPAN = '<span class="fender-ui_0cb57fb2">새 창 열림</span>'


class ParseSearchResultsHiddenLabelTest(unittest.TestCase):
    def test_title_and_snippet_do_not_leak_new_window_accessibility_label(self):
        html = make_anchor(
            "testuser1",
            "223456789012",
            '<span class="sds-comps-text-type-headline1">테스트 제목입니다</span>' + NEW_WINDOW_LABEL_SPAN,
        ) + make_anchor(
            "testuser1",
            "223456789012",
            '<span class="sds-comps-text-type-body1">테스트 스니펫 본문입니다.</span>'
            + '<span class="fender-ui_44bf8dba">새 창 열림</span>',
        )

        results = naver_search.parse_search_results(html)

        self.assertEqual(len(results), 1)
        self.assertEqual(results[0]["title"], "테스트 제목입니다")
        self.assertEqual(results[0]["snippet"], "테스트 스니펫 본문입니다.")

    def test_label_glued_without_whitespace_is_removed(self):
        html = make_anchor(
            "testuser2",
            "223456789013",
            '<span class="sds-comps-text-type-headline1">제주도한우' + NEW_WINDOW_LABEL_SPAN + "</span>",
        )

        results = naver_search.parse_search_results(html)

        self.assertEqual(results[0]["title"], "제주도한우")

    def test_legitimate_text_containing_the_phrase_is_preserved(self):
        html = make_anchor(
            "testuser3",
            "223456789014",
            '<span class="sds-comps-text-type-headline1">"새 창 열림" 안 될 때 해결법</span>' + NEW_WINDOW_LABEL_SPAN,
        )

        results = naver_search.parse_search_results(html)

        self.assertEqual(results[0]["title"], '"새 창 열림" 안 될 때 해결법')


class SearchWorkflowTest(unittest.TestCase):
    def test_search_uses_15_result_pages_and_ignores_extra_anchors_beyond_page_window(self):
        fetch_starts: list[int] = []
        parsed_pages = {
            "page-1": [make_result(index) for index in range(1, 16)] + [make_result(101), make_result(102)],
            "page-16": [make_result(index) for index in range(16, 31)] + [make_result(101), make_result(102)],
        }

        def fake_fetch(query: str, start: int = 1, sort: str = "sim", timeout: int = 15, *, insecure: bool = False) -> str:
            self.assertEqual(query, "서울 맛집")
            self.assertEqual(sort, "sim")
            self.assertEqual(timeout, 15)
            self.assertFalse(insecure)
            fetch_starts.append(start)
            return f"page-{start}"

        def fake_parse(html: str) -> list[dict]:
            return parsed_pages[html]

        with (
            mock.patch.object(naver_search, "fetch_search_page", side_effect=fake_fetch),
            mock.patch.object(naver_search, "parse_search_results", side_effect=fake_parse),
            mock.patch.object(naver_search.time, "sleep"),
        ):
            result = naver_search.search("서울 맛집", count=20)

        self.assertEqual(fetch_starts, [1, 16])
        self.assertEqual(result["total_results"], 20)
        self.assertEqual(
            [item["url"] for item in result["results"]],
            [make_result(index)["url"] for index in range(1, 21)],
        )

    def test_search_passes_date_sort_through_to_fetcher(self):
        captured_sorts: list[str] = []

        def fake_fetch(query: str, start: int = 1, sort: str = "sim", timeout: int = 15, *, insecure: bool = False) -> str:
            captured_sorts.append(sort)
            return "page-1"

        with (
            mock.patch.object(naver_search, "fetch_search_page", side_effect=fake_fetch),
            mock.patch.object(naver_search, "parse_search_results", return_value=[make_result(1)]),
        ):
            result = naver_search.search("서울 맛집", count=1, sort="date")

        self.assertEqual(captured_sorts, ["date"])
        self.assertEqual(result["results"][0]["url"], make_result(1)["url"])


if __name__ == "__main__":
    unittest.main()
