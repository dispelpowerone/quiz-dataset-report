from quiz_dataset_report.images import embed_images

HTML = (
    '<div><img class="q-img" src="https://pi.local/api/images/on/1.png" alt="x">'
    '<img class="q-img" src="https://pi.local/api/images/on/2.png">'
    '<img class="q-img" src="https://pi.local/api/images/on/1.png"></div>'
)


def test_embeds_and_rewrites_to_cid():
    calls = []

    def fetch(url):
        calls.append(url)
        return "image/png", b"\x89PNG-" + url[-5:].encode()

    out, images = embed_images(HTML, fetch)

    # two unique URLs -> two images; duplicate URL fetched once
    assert len(images) == 2
    assert len(calls) == 2
    # no remote URLs remain; cid references injected
    assert "https://pi.local" not in out
    assert out.count("cid:img0@quiz-dataset-report") == 2  # both dupes rewritten
    assert "cid:img1@quiz-dataset-report" in out
    assert images[0].maintype == "image" and images[0].subtype == "png"


def test_failed_fetch_keeps_url():
    def fetch(url):
        return None if url.endswith("2.png") else ("image/png", b"data")

    out, images = embed_images(HTML, fetch)
    assert len(images) == 1
    # the failed one keeps its original URL
    assert "https://pi.local/api/images/on/2.png" in out
    assert "https://pi.local/api/images/on/1.png" not in out
