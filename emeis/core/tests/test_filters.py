import pytest
from django.urls import reverse
from django.utils import translation
from rest_framework import status

from emeis.core.models import User


@pytest.mark.parametrize(
    "user_attribute",
    [
        lambda u: u.first_name,
        lambda u: u.last_name,
        lambda u: u.acls.first().scope.name,
        lambda u: u.acls.first().role.name,
    ],
)
@pytest.mark.parametrize(
    "partial_search", [lambda val: val[:-2], lambda val: val[2:], lambda val: val]
)
def test_search_users(admin_client, acl_factory, user_attribute, partial_search):

    users_list = [acl.user for acl in acl_factory.create_batch(5)]

    resp = admin_client.get(
        reverse("user-list"),
        {"filter[search]": partial_search(str(user_attribute(users_list[0])))},
    )
    returned_user_ids = [us["id"] for us in resp.json()["data"]]

    assert str(users_list[0].pk) in returned_user_ids
    # ensure we don't just return the full user list
    assert len(returned_user_ids) < len(users_list)


@pytest.mark.parametrize(
    "filter_name, expect_result",
    [("hasRole", True), ("has_role", True), ("hasrole", False)],
)
def test_user_has_role(admin_client, acl_factory, filter_name, expect_result):
    users_list = [acl.user for acl in acl_factory.create_batch(3)]

    resp = admin_client.get(
        reverse("user-list"),
        {f"filter[{filter_name}]": users_list[2].acls.first().role_id},
    )

    if expect_result:
        ret_users = [us["attributes"]["username"] for us in resp.json()["data"]]
        expected = [str(users_list[2].username)]

        assert expected == ret_users
    else:
        assert resp.status_code == status.HTTP_400_BAD_REQUEST


@pytest.mark.parametrize(
    "filter_field, model_attr, expect_result",
    [
        ("id__in", "pk", True),
        ("id", "pk", True),
        ("username", "username", True),
        ("username", "email", False),
        ("email__in", "email", True),
        ("email__in", "username", False),
    ],
)
def test_declared_filters(
    admin_client, user_factory, filter_field, model_attr, expect_result
):
    user1, _ = user_factory.create_batch(2)

    attr_value = getattr(user1, model_attr)

    resp = admin_client.get(
        reverse("user-list"), {f"filter[{filter_field}]": attr_value}
    )

    ret_users = [us["attributes"]["username"] for us in resp.json()["data"]]

    if expect_result:
        assert [user1.username] == ret_users
    else:
        assert ret_users == []


@pytest.mark.parametrize("sort", ["email", "-email"])
def test_user_ordering_case_insensitive(admin_client, admin_user, user_factory, sort):
    emails = [
        "Aaaa@example.com",
        "Zzzzz@example.com",
        "aaaaa@example.com",
        "m@example.com",
    ]
    for email in emails:
        user_factory.create(email=email)

    resp = admin_client.get(reverse("user-list"), {"sort": sort})

    expect_emails = sorted(
        emails + [admin_user.user.email],
        key=lambda e: e.lower(),
        reverse=sort.startswith("-"),
    )

    assert expect_emails == [d["attributes"]["email"] for d in resp.json()["data"]]


@pytest.mark.parametrize("sort", ["username", "-username"])
def test_user_ordering_case_sensitive(admin_client, admin_user, user_factory, sort):
    user_factory.create_batch(5)

    resp = admin_client.get(reverse("user-list"), {"sort": sort})

    expected = list(
        User.objects.all().order_by(sort).values_list("username", flat=True)
    )

    assert expected == [d["attributes"]["username"] for d in resp.json()["data"]]


@pytest.mark.parametrize(
    "force_lang, search_term, expect_result",
    [
        ("de", "deutscher", 1),
        ("de", "english", 0),
        ("en", "deutscher", 0),
        ("en", "english", 1),
        (None, "deutscher", 0),
        (None, "english", 1),
    ],
)
def test_search_monolingual(
    settings, admin_client, role_factory, force_lang, search_term, expect_result
):
    role_factory(name={"de": "deutscher name", "en": "english name"})

    if force_lang:
        settings.EMEIS_FORCE_MODEL_LOCALE = {"role": force_lang}

    with translation.override("en"):
        resp = admin_client.get(reverse("role-list"), {"filter[search]": search_term})

    assert len(resp.json()["data"]) == expect_result
