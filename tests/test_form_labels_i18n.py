"""Nhãn ô trên form tạo / sửa phải theo ngôn ngữ đang chọn, không ghi cứng tiếng Việt."""

from __future__ import annotations

import re

import pytest

from tests.test_so_tong_edit import admin_client, client, override_db  # noqa: F401


def _labels(html: str) -> list[str]:
    return [re.sub(r"\s+", " ", t).strip() for t in re.findall(r"<label[^>]*>(.*?)</label>", html, re.S)]


@pytest.mark.parametrize("lang, expected, forbidden", [
    ("en", "Employee Full Name", "Họ và tên nhân viên"),
    ("ja", None, "Họ và tên nhân viên"),
    ("vi", "Họ và tên nhân viên", None),
])
def test_form_sua_nhan_su_theo_ngon_ngu(admin_client, db, seed, lang, expected, forbidden):  # noqa: F811
    admin_client.cookies.set("itam_lang", lang)
    labels = _labels(admin_client.get(f"/admin/person/edit/{seed['person'].id}").text)
    assert labels
    if expected:
        assert expected in labels, labels
    if forbidden:
        assert forbidden not in labels, labels
    if lang != "vi":
        assert not any(w in " ".join(labels) for w in ("Tình trạng", "Ngày vào làm việc", "Ghi chú")), labels


def test_form_tao_thiet_bi_tieng_anh(admin_client, db, seed):  # noqa: F811
    admin_client.cookies.set("itam_lang", "en")
    html = admin_client.get("/admin/asset/create").text
    assert "Ghi chú" not in " ".join(_labels(html))
    assert "Lưu" not in html.split("<form", 1)[1]


_VI = re.compile(r"[ăâđêôơưạảấầẩẫậắằẳẵặẹẻẽếềểễệỉịọỏốồổỗộớờởỡợụủứừửữựỳỵỷỹ]", re.I)


@pytest.mark.parametrize("lang", ["en", "ja"])
@pytest.mark.parametrize("path", [
    "/admin/person/create", "/admin/asset/create", "/admin/assignment/create", "/admin/user/create",
    "/admin/asset-category/create", "/admin/department/create",
])
def test_moi_form_khong_con_nhan_tieng_viet(admin_client, db, seed, lang, path):  # noqa: F811
    admin_client.cookies.set("itam_lang", lang)
    res = admin_client.get(path)
    assert res.status_code == 200, path
    form = res.text.split("<form", 1)[1].split("</form>", 1)[0]
    texts = _labels(form) + [re.sub(r"\s+", " ", t).strip() for t in re.findall(r'<small class="text-muted">(.*?)</small>', form, re.S)]
    leftover = [t for t in texts if _VI.search(t)]
    assert not leftover, leftover
