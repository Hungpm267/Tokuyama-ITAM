import pytest
from django.urls import reverse
from django.conf import settings

@pytest.mark.django_db
def test_language_switch_sets_cookie_and_redirects(client):
    url = reverse("set_language")
    response = client.post(url, data={
        "language": "ja",
        "next": reverse("admin:index")
    })
    assert response.status_code == 302
    assert response.cookies[settings.LANGUAGE_COOKIE_NAME].value == "ja"

@pytest.mark.django_db
def test_japanese_session_renders_japanese_response(client):
    client.cookies[settings.LANGUAGE_COOKIE_NAME] = "ja"
    response = client.get(reverse("admin:login"))
    assert response.status_code == 200
