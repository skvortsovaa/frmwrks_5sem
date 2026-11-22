"""Планирование проверок через Django Forms без изменения истории."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required, permission_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_http_methods, require_POST

from smartspace_web.query_params import database_page
from .forms import InspectionFilterForm, InspectionPlanForm
from .models import InspectionPlan


@database_page
@require_http_methods(["GET"])
def plan_list(request):
    # Без query string показываем активные планы. Явный status= даёт все.
    params = request.GET if request.GET else {"status": "planned"}
    form = InspectionFilterForm(params)
    plans = InspectionPlan.objects.select_related("room", "created_by")
    per_page = 10
    if form.is_valid():
        data = form.cleaned_data
        for field, lookup in (("date", "inspection_date"),
                              ("room", "room"), ("author", "created_by"),
                              ("status", "status")):
            if data[field]:
                plans = plans.filter(**{lookup: data[field]})
        orders = {"date": ("inspection_date", "pk"),
                  "-date": ("-inspection_date", "pk"),
                  "room": ("room__name", "inspection_date", "pk")}
        plans = plans.order_by(*orders[data["sort"] or "date"])
        per_page = data["per_page"] or 10
    else:
        plans = plans.none()
    page = Paginator(plans, per_page).get_page(request.GET.get("page"))
    return render(request, "reports_web/plan_list.html", {
        "form": form, "page_obj": page,
    })


def _edit_plan(request, plan=None):
    form = InspectionPlanForm(
        request.POST if request.method == "POST" else None, instance=plan,
    )
    if request.method == "POST" and form.is_valid():
        try:
            with transaction.atomic():
                obj = form.save(commit=False)
                if plan is None:
                    obj.created_by = request.user
                obj.save()
        except IntegrityError:
            form.add_error(None, "Дата уже занята. Обновите форму.")
        else:
            messages.success(request, "План проверки сохранён.")
            return redirect("inspections:list")
    return render(request, "reports_web/plan_form.html", {
        "form": form, "plan": plan,
    })


@database_page
@login_required
@permission_required("reports_web.add_inspectionplan", raise_exception=True)
@require_http_methods(["GET", "POST"])
def plan_create(request):
    return _edit_plan(request)


@database_page
@login_required
@permission_required("reports_web.change_inspectionplan", raise_exception=True)
@require_http_methods(["GET", "POST"])
def plan_edit(request, pk):
    # Блокировка сохраняется до окончания POST, включая повторную валидацию.
    with transaction.atomic():
        plan = get_object_or_404(
            InspectionPlan.objects.select_for_update().select_related("room"),
            pk=pk,
        )
        if plan.status != InspectionPlan.Status.PLANNED:
            messages.error(request, "Отменённый план нельзя редактировать.")
            return redirect("inspections:list")
        return _edit_plan(request, plan)


@database_page
@login_required
@permission_required("reports_web.change_inspectionplan", raise_exception=True)
@require_POST
def plan_cancel(request, pk):
    plan = get_object_or_404(InspectionPlan, pk=pk)
    plan.cancel()
    messages.success(request, "План отменён. Запись сохранена в истории.")
    return redirect("inspections:list")
