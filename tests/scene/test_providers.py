import os
from pathlib import Path
import sys
import unittest
from unittest.mock import patch

import httpx

sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "backend"))
from app.features.scene.matterport import get_model
from app.features.scene.providers import ProviderError
from app.features.scene.vexcel import aerial_request, get_aerial


class ProviderTests(unittest.TestCase):
    @patch.dict(os.environ, {"VEXCEL_API_KEY": "test-secret"})
    @patch("app.features.scene.vexcel.httpx.post")
    def test_image_credentials_stay_in_header(self, post):
        post.return_value = httpx.Response(200, content=b"\xff\xd8\xffimage")
        image, mime = get_aerial(40.3, -74.6)
        self.assertEqual(mime, "image/jpeg")
        self.assertTrue(image)
        args, kwargs = post.call_args
        self.assertEqual(kwargs["headers"], {"X-API-KEY": "test-secret"})
        self.assertNotIn("test-secret", args[0])
        self.assertNotIn("test-secret", str(kwargs["json"]))
        self.assertEqual(kwargs["json"]["srid"], 4326)

    def test_aerial_bounds_use_longitude_first(self):
        body = aerial_request(40.3, -74.6)
        coordinates = body["wkt"].removeprefix("POLYGON((").removesuffix("))").split(",")
        points = [tuple(map(float, point.split())) for point in coordinates]
        self.assertEqual(points[0], points[-1])
        self.assertTrue(all(-75 < lon < -74 and 40 < lat < 41 for lon, lat in points))

    def test_invalid_coordinates_cannot_trigger_requests(self):
        for lat, lon in [(float("nan"), 0), (0, float("inf")), (90, 0), (0, 181)]:
            with self.subTest(lat=lat, lon=lon), self.assertRaises(ProviderError):
                aerial_request(lat, lon)

    @patch.dict(os.environ, {"VEXCEL_API_KEY": "test-secret"})
    @patch("app.features.scene.vexcel.time.sleep")
    @patch("app.features.scene.vexcel.httpx.post")
    def test_rate_limit_retry_is_bounded(self, post, sleep):
        post.return_value = httpx.Response(429)
        with self.assertRaisesRegex(ProviderError, "rate limiting"):
            get_aerial(40.3, -74.6)
        self.assertEqual(post.call_count, 3)
        self.assertEqual(sleep.call_count, 2)

    @patch.dict(os.environ, {"VEXCEL_API_KEY": "test-secret"})
    @patch("app.features.scene.vexcel.httpx.post")
    def test_no_coverage_and_nonimage_response_are_explicit(self, post):
        post.return_value = httpx.Response(404)
        with self.assertRaises(ProviderError) as error:
            get_aerial(40.3, -74.6)
        self.assertEqual(error.exception.status_code, 404)
        post.return_value = httpx.Response(200, json={"error": "not an image"})
        with self.assertRaisesRegex(ProviderError, "unexpected image"):
            get_aerial(40.3, -74.6)

    @patch.dict(os.environ, {"MATTERPORT_API_KEY": "test-id", "MATTERPORT_API_TOKEN": "test-secret",
                             "VITE_MATTERPORT_MODEL_ID": "P3S6VUTP3qB"})
    @patch("app.features.scene.matterport.httpx.post")
    def test_graphql_errors_do_not_leak_provider_details(self, post):
        post.return_value = httpx.Response(200, json={"errors": [{"message": "test-secret"}], "data": None})
        with self.assertRaises(ProviderError) as error:
            get_model()
        self.assertNotIn("test-secret", str(error.exception))
        self.assertEqual(post.call_args.kwargs["auth"], ("test-id", "test-secret"))


if __name__ == "__main__":
    unittest.main()
