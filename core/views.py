from datetime import date, timedelta
from django.shortcuts import render, get_object_or_404, redirect
from django.contrib import messages
from django.contrib.admin.views.decorators import staff_member_required
from django.utils.translation import gettext as _
from django.db.models import Q

from apps.organization.models import Person
from apps.assets.models import Asset, Assignment
from apps.licenses.models import License, LicenseAssignment
from apps.cards.models import AccessCard, CardLoan
from apps.contracts.models import Contract


def get_dashboard_context():
    today = date.today()
    in_60_days = today + timedelta(days=60)

    # 1. Thống kê Thiết bị
    total_assets = Asset.objects.count()
    in_stock_assets = Asset.objects.filter(status='in_stock').count()
    loaned_assets = Asset.objects.filter(status='loaned').count()
    lost_assets = Asset.objects.filter(status='lost').count()

    asset_stats = {
        'total': total_assets,
        'in_stock': in_stock_assets,
        'loaned': loaned_assets,
        'lost': lost_assets,
    }

    # 2. Cảnh báo License sắp hết hạn (trong 60 ngày hoặc đã hết hạn)
    expiring_licenses = License.objects.filter(
        expiry_date__isnull=False,
        expiry_date__lte=in_60_days
    ).select_related('product').order_by('expiry_date')

    expiring_list = []
    for lic in expiring_licenses:
        days_left = (lic.expiry_date - today).days
        expiring_list.append({
            'license': lic,
            'days_left': days_left,
            'is_expired': days_left < 0,
        })

    # 3. Thẻ ra vào đang cho mượn chưa trả
    unreturned_cards = CardLoan.objects.filter(
        returned_at__isnull=True
    ).select_related('card', 'person').prefetch_related('card__rooms')

    return {
        'asset_stats': asset_stats,
        'expiring_licenses': expiring_list,
        'unreturned_cards': unreturned_cards,
    }


@staff_member_required
def global_search_view(request):
    query = request.GET.get('q', '').strip()
    results = {
        'query': query,
        'assets': [],
        'persons': [],
        'contracts': [],
        'cards': [],
        'total_count': 0,
    }

    if query:
        assets = Asset.objects.filter(
            Q(asset_code__icontains=query) |
            Q(serial__icontains=query) |
            Q(hwid__icontains=query) |
            Q(mac_address__icontains=query) |
            Q(model__icontains=query)
        ).select_related('category')[:20]

        persons = Person.objects.filter(
            Q(staff_code__icontains=query) |
            Q(full_name__icontains=query)
        ).select_related('department')[:20]

        contracts = Contract.objects.filter(
            Q(code__icontains=query)
        )[:20]

        cards = AccessCard.objects.filter(
            Q(card_no__icontains=query)
        )[:20]

        results['assets'] = assets
        results['persons'] = persons
        results['contracts'] = contracts
        results['cards'] = cards
        results['total_count'] = len(assets) + len(persons) + len(contracts) + len(cards)

    context = {
        **results,
        'title': _('Tìm kiếm toàn cục / Global Search'),
    }
    return render(request, 'admin/global_search.html', context)


@staff_member_required
def person_profile_view(request, person_id):
    person = get_object_or_404(Person, pk=person_id)

    # 1. Thiết bị đang giữ
    current_assignments = Assignment.objects.filter(
        person=person,
        returned_at__isnull=True
    ).select_related('asset', 'asset__category')

    # 2. Lịch sử thiết bị đã từng mượn
    past_assignments = Assignment.objects.filter(
        person=person,
        returned_at__isnull=False
    ).select_related('asset', 'asset__category').order_by('-returned_at')

    # 3. License đang được gán (gán trực tiếp cho người hoặc máy người này đang giữ)
    current_asset_ids = [a.asset_id for a in current_assignments]
    licenses_assigned = LicenseAssignment.objects.filter(
        Q(person=person) | Q(asset_id__in=current_asset_ids),
        removed_at__isnull=True
    ).select_related('license', 'license__product', 'asset')

    # 4. Thẻ ra vào
    current_card_loans = CardLoan.objects.filter(
        person=person,
        returned_at__isnull=True
    ).select_related('card').prefetch_related('card__rooms')

    past_card_loans = CardLoan.objects.filter(
        person=person,
        returned_at__isnull=False
    ).select_related('card').order_by('-returned_at')

    context = {
        'person': person,
        'current_assignments': current_assignments,
        'past_assignments': past_assignments,
        'licenses_assigned': licenses_assigned,
        'current_card_loans': current_card_loans,
        'past_card_loans': past_card_loans,
        'title': _(f'Hồ sơ Tài sản IT: {person.full_name} ({person.staff_code})'),
    }
    return render(request, 'admin/person_profile.html', context)


@staff_member_required
def trash_management_view(request):
    if not request.user.is_superuser and not request.user.groups.filter(name='IT Admin').exists():
        messages.error(request, _('Bạn không có quyền truy cập Thùng rác.'))
        return redirect('admin:index')

    if request.method == 'POST' and 'restore_item' in request.POST:
        model_name = request.POST.get('model_name')
        item_id = request.POST.get('item_id')

        model_map = {
            'asset': Asset,
            'person': Person,
            'license': License,
            'card': AccessCard,
            'contract': Contract,
        }
        target_model = model_map.get(model_name)
        if target_model:
            item = target_model.all_objects.filter(pk=item_id, is_deleted=True).first()
            if item:
                item.restore()
                messages.success(request, _(f'Đã khôi phục thành công: {item}'))
            else:
                messages.error(request, _('Không tìm thấy bản ghi cần khôi phục.'))
        return redirect('admin:trash')

    # Query soft-deleted items across models
    deleted_assets = Asset.all_objects.filter(is_deleted=True).select_related('category', 'deleted_by')
    deleted_persons = Person.all_objects.filter(is_deleted=True).select_related('department', 'deleted_by')
    deleted_licenses = License.all_objects.filter(is_deleted=True).select_related('product', 'deleted_by')
    deleted_cards = AccessCard.all_objects.filter(is_deleted=True).select_related('deleted_by')
    deleted_contracts = Contract.all_objects.filter(is_deleted=True).select_related('deleted_by')

    items = []
    for a in deleted_assets:
        items.append({'model_name': 'asset', 'type': _('Tài sản'), 'name': str(a), 'obj': a})
    for p in deleted_persons:
        items.append({'model_name': 'person', 'type': _('Nhân viên'), 'name': str(p), 'obj': p})
    for l in deleted_licenses:
        items.append({'model_name': 'license', 'type': _('License'), 'name': str(l), 'obj': l})
    for c in deleted_cards:
        items.append({'model_name': 'card', 'type': _('Thẻ từ'), 'name': str(c), 'obj': c})
    for ct in deleted_contracts:
        items.append({'model_name': 'contract', 'type': _('Hợp đồng'), 'name': str(ct), 'obj': ct})

    context = {
        'items': items,
        'title': _('Thùng rác & Khôi phục bản ghi / Trash & Restore'),
    }
    return render(request, 'admin/trash.html', context)
