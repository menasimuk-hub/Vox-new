"""Static-host crawler files (sitemap.xml / robots.txt) served by the API."""


def test_sitemap_and_robots_plain_endpoints(app_client):
    robots = app_client.get("/frontpage/seo/robots-plain")
    assert robots.status_code == 200
    assert "text/plain" in robots.headers.get("content-type", "")
    assert "User-agent" in robots.text
    assert "Sitemap:" in robots.text

    sitemap = app_client.get("/frontpage/seo/sitemap.xml")
    assert sitemap.status_code == 200
    assert "xml" in sitemap.headers.get("content-type", "")
    assert "<urlset" in sitemap.text
    assert "<loc>https://voxbulk.com/</loc>" in sitemap.text
    assert sitemap.text.strip().startswith("<?xml")

    news = app_client.get("/frontpage/seo/news-sitemap.xml")
    assert news.status_code == 200
    assert "<urlset" in news.text
    assert news.text.strip().startswith("<?xml")
