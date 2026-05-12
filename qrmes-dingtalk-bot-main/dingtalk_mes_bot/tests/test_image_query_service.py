import unittest

from dingtalk_mes_bot.models import DownloadedImage, PrefixMatch, SerialQueryResult, VisionRecognitionResult
from dingtalk_mes_bot.services.image_query_service import ImageQueryService


class FakeImageDownloader:
    def __init__(self, images):
        self.images = images
        self.calls = []

    def download_images(self, download_codes):
        self.calls.append(tuple(download_codes))
        return self.images


class FakeVisionService:
    def __init__(self, result):
        self.result = result
        self.calls = []

    def recognize(self, images, user_text=""):
        self.calls.append((tuple(image.download_code for image in images), user_text))
        return self.result


class FakePrefixService:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def resolve(self, serial):
        self.calls.append(serial)
        return list(self.mapping.get(serial, ()))

    def resolve_for_query(self, serial):
        self.calls.append(serial)
        return serial, tuple(self.mapping.get(serial, ()))


class FakeMesQueryService:
    def __init__(self, mapping):
        self.mapping = mapping
        self.calls = []

    def query_serial_database(self, serial, prefix_matches=()):
        self.calls.append((serial, tuple(prefix_matches)))
        return self.mapping.get(serial)


class ImageQueryServiceTests(unittest.TestCase):
    def test_queries_each_detected_serial(self):
        service = ImageQueryService(
            image_downloader=FakeImageDownloader(
                [DownloadedImage(download_code="img1", mime_type="image/jpeg", data=b"image-bytes")]
            ),
            vision_service=FakeVisionService(
                VisionRecognitionResult(
                    serial_numbers=("SERIAL-001", "SERIAL-002"),
                    product_type_names=("Controller-2in1",),
                    raw_qr_texts=("SERIAL-001", "SERIAL-002"),
                    notes=("label visible",),
                )
            ),
            prefix_service=FakePrefixService(
                {
                    "SERIAL-001": (
                        PrefixMatch(project_name="Project-A", product_type="Product-A", prefix="SERIAL", length=6),
                    ),
                    "SERIAL-002": (
                        PrefixMatch(project_name="Project-B", product_type="Product-B", prefix="SERIAL", length=6),
                    ),
                }
            ),
            mes_query_service=FakeMesQueryService(
                {
                    "SERIAL-001": SerialQueryResult(
                        serial="SERIAL-001",
                        found=True,
                        project_name="Project-A",
                        product_type="Product-A",
                        quality_summary="ready",
                        process_summary="10 processes checked; 0 photos missing",
                    ),
                    "SERIAL-002": SerialQueryResult(
                        serial="SERIAL-002",
                        found=True,
                        project_name="Project-B",
                        product_type="Product-B",
                        quality_summary="review",
                        process_summary="7 processes checked; 2 photos missing",
                    ),
                }
            ),
        )

        reply = service.reply_for_images(("img1",), user_text="Please check all QR labels")

        self.assertIn("2", reply)
        self.assertIn("SERIAL-001", reply)
        self.assertIn("SERIAL-002", reply)
        self.assertIn("Project-A", reply)
        self.assertIn("Project-B", reply)

    def test_returns_recognition_result_when_no_serial_detected(self):
        service = ImageQueryService(
            image_downloader=FakeImageDownloader(
                [DownloadedImage(download_code="img1", mime_type="image/jpeg", data=b"image-bytes")]
            ),
            vision_service=FakeVisionService(
                VisionRecognitionResult(
                    serial_numbers=(),
                    product_type_names=("Controller-2in1",),
                    raw_qr_texts=(),
                    notes=("only product name detected",),
                )
            ),
            prefix_service=FakePrefixService({}),
            mes_query_service=FakeMesQueryService({}),
        )

        reply = service.reply_for_images(("img1",), user_text="What is on this label")

        self.assertIn("Controller-2in1", reply)

    def test_ignores_unmatched_non_serial_values(self):
        service = ImageQueryService(
            image_downloader=FakeImageDownloader(
                [DownloadedImage(download_code="img1", mime_type="image/jpeg", data=b"image-bytes")]
            ),
            vision_service=FakeVisionService(
                VisionRecognitionResult(
                    serial_numbers=("SERIAL-001", "MO001104"),
                    product_type_names=("Controller-2in1",),
                    raw_qr_texts=("SERIAL-001", "MO001104"),
                    notes=(),
                )
            ),
            prefix_service=FakePrefixService(
                {
                    "SERIAL-001": (
                        PrefixMatch(project_name="Project-A", product_type="Product-A", prefix="SERIAL", length=6),
                    ),
                }
            ),
            mes_query_service=FakeMesQueryService(
                {
                    "SERIAL-001": SerialQueryResult(
                        serial="SERIAL-001",
                        found=True,
                        project_name="Project-A",
                        product_type="Product-A",
                        quality_summary="ready",
                        process_summary="10 processes checked; 0 photos missing",
                    ),
                    "MO001104": SerialQueryResult(
                        serial="MO001104",
                        found=False,
                        quality_summary="record not found",
                        process_summary="no process",
                    ),
                }
            ),
        )

        reply = service.reply_for_images(("img1",), user_text="Check this image")

        self.assertIn("SERIAL-001", reply)
        self.assertNotIn("MO001104", reply)


if __name__ == "__main__":
    unittest.main()
