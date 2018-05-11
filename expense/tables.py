# coding: utf-8
"""
Pydici leads tables
@author: Sébastien Renard (sebastien.renard@digitalfox.org)
@license: AGPL v3 or newer (http://www.gnu.org/licenses/agpl-3.0.html)
"""

from django.utils.translation import ugettext as _
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.utils.safestring import mark_safe
from django.utils.encoding import smart_bytes
from django.template import Template, RequestContext
from django.template.loader import get_template
from django_datatables_view.base_datatable_view import BaseDatatableView

import django_tables2 as tables
from django_tables2.utils import A

from expense.models import Expense, ExpensePayment
from core.templatetags.pydici_filters import link_to_consultant
from core.utils import TABLES2_HIDE_COL_MD, to_int_or_round
from core.decorator import PydiciFeatureMixin, PydiciNonPublicdMixin


class ExpenseTableDT(PydiciNonPublicdMixin, PydiciFeatureMixin, BaseDatatableView):
    """Expense table backend for datatable"""
    pydici_feature = set(["reports"])
    columns = ["pk", "user", "category", "description", "lead", "amount", "receipt", "chargeable", "corporate_card", "state", "creation_date", "expense_date", "update_date", "comment"]
    order_columns = columns
    max_display_length = 500
    date_template = get_template("core/_date_column.html")
    receipt_template = get_template("expense/_receipt_column.html")
    state_template = get_template("expense/_expense_state_column.html")
    ko_sign = mark_safe("""<span class="glyphicon glyphicon-remove" style="color:red"></span>""")
    ok_sign = mark_safe("""<span class="glyphicon glyphicon-ok" style="color:green"></span>""")

    def get_initial_queryset(self):
        return Expense.objects.all().select_related("lead__client__contact", "lead__client__organisation__company", "user")

    def filter_queryset(self, qs):
        """ simple search on some attributes"""
        search = self.request.GET.get(u'search[value]', None)
        if search:
            qs = qs.filter(Q(comment__icontains=search) |
                           Q(description__icontains=search) |
                           Q(user__first_name__icontains=search) |
                           Q(user__last_name__icontains=search) |
                           Q(user__username=search) |
                           Q(lead__client__organisation__company__name__icontains=search) |
                           Q(lead__client__organisation__name__iexact=search) |
                           Q(lead__description__icontains=search) |
                           Q(lead__deal_id__icontains=search))
            qs = qs.distinct()
        return qs

    def render_column(self, row, column):
        if column == "user":
            return link_to_consultant(row.user)
        elif column == "receipt":
            return self.receipt_template.render(RequestContext(self.request, {"record": row}))
        elif column == "lead":
            if row.lead:
                return u"<a href='{0}'>{1}</a>".format(row.lead.get_absolute_url(), row.lead)
            else:
                return u"-"
        elif column in ("creation_date", "expense_date"):
            return self.date_template.render({"date": getattr(row, column)})
        elif column == "update_date":
            return row.update_date.strftime("%x %X")
        elif column in ("chargeable", "corporate_card"):
            if getattr(row, column):
                return self.ok_sign
            else:
                return self.ko_sign
        elif column == "state":
            return self.state_template.render(RequestContext(self.request, {"record": row}))
        elif column == "amount":
            return to_int_or_round(row.amount, 2)
        else:
            return super(ExpenseTableDT, self).render_column(row, column)



class ExpenseTable(tables.Table):
    user = tables.Column(verbose_name=_("Consultant"))
    lead = tables.TemplateColumn("""{% if record.lead %}<a href='{% url "leads.views.detail" record.lead.id %}'>{{ record.lead }}</a>{% endif%}""")
    receipt = tables.TemplateColumn(template_name="expense/_receipt_column.html")
    state = tables.TemplateColumn(template_name="expense/_expense_state_column.html", orderable=False)
    expense_date = tables.TemplateColumn("""<span title="{{ record.expense_date|date:"Ymd" }}">{{ record.expense_date }}</span>""")  # Title attr is just used to have an easy to parse hidden value for sorting
    update_date = tables.TemplateColumn("""<span title="{{ record.update_date|date:"Ymd" }}">{{ record.update_date }}</span>""", attrs=TABLES2_HIDE_COL_MD)  # Title attr is just used to have an easy to parse hidden value for sorting


    def render_user(self, value):
        return link_to_consultant(value)

    class Meta:
        model = Expense
        sequence = ("user", "description", "lead", "amount", "chargeable", "corporate_card", "receipt", "state", "expense_date", "update_date", "comment")
        fields = sequence
        attrs = {"class": "pydici-tables2 table table-hover table-striped table-condensed", "id": "expense_table"}
        orderable = False
        order_by = "-expense_date"


class ExpenseWorkflowTable(ExpenseTable):
    transitions = tables.Column(accessor="pk")

    def render_transitions(self, record):
        result = []
        for transition in self.transitionsData[record.id]:
            result.append("""<a href="javascript:;" onClick="$.get('%s', process_expense_transition)">%s</a>"""
                          % (reverse("expense.views.update_expense_state", args=[record.id, transition.id]), transition))
        if self.expenseEditPerm[record.id]:
            result.append("<a href='%s'>%s</a>" % (reverse("expense.views.expenses", kwargs={"expense_id": record.id}), smart_bytes(_("Edit"))))
        result.append("<a href='%s'>%s</a>" % (reverse("expense.views.expenses", kwargs={"clone_from": record.id}), smart_bytes(_("Clone"))))
        return mark_safe(", ".join(result))

    class Meta:
        sequence = ("user", "description", "lead", "amount", "chargeable", "corporate_card", "receipt", "state", "transitions", "expense_date", "update_date", "comment")
        fields = sequence


class UserExpenseWorkflowTable(ExpenseWorkflowTable):
    class Meta:
        attrs = {"class": "pydici-tables2 table table-hover table-striped table-condensed", "id": "user_expense_workflow_table"}
        prefix = "user_expense_workflow_table"
        orderable = False


class ManagedExpenseWorkflowTable(ExpenseWorkflowTable):
    description = tables.TemplateColumn("""{% load l10n %} <span id="managed_expense_{{record.id|unlocalize }}">{{ record.description }}</span>""")
    class Meta:
        attrs = {"class": "pydici-tables2 table table-hover table-striped table-condensed", "id": "managed_expense_workflow_table"}
        prefix = "managed_expense_workflow_table"
        orderable = False


class ExpensePaymentTable(tables.Table):
    user = tables.Column(verbose_name=_("Consultant"), orderable=False)
    amount = tables.Column(verbose_name=_("Amount"), orderable=False)
    id = tables.LinkColumn(viewname="expense.views.expense_payment_detail", args=[A("pk")])
    detail = tables.TemplateColumn("""<a href="{% url 'expense.views.expense_payment_detail' record.id %}"><img src='{{MEDIA_URL}}pydici/menu/magnifier.png'/></a>""", verbose_name=_("detail"), orderable=False)
    modify = tables.TemplateColumn("""<a href="{% url 'expense.views.expense_payments' record.id %}"><img src='{{MEDIA_URL}}img/icon_changelink.gif'/></a>""", verbose_name=_("change"), orderable=False)
    payment_date = tables.TemplateColumn("""<span title="{{ record.payment_date|date:"Ymd" }}">{{ record.payment_date }}</span>""")  # Title attr is just used to have an easy to parse hidden value for sorting

    def render_user(self, value):
        return link_to_consultant(value)

    class Meta:
        model = ExpensePayment
        sequence = ("id", "user", "amount", "payment_date")
        fields = sequence
        attrs = {"class": "pydici-tables2 table table-hover table-striped table-condensed", "id": "expense_payment_table"}
        order_by = "-id"
        orderable = False

class ExpensePaymentTableDT(PydiciNonPublicdMixin, PydiciFeatureMixin, BaseDatatableView):
    """Expense payment table backend for datatable"""
    pydici_feature = set(["reports"])
    columns = ["pk", "user",  "amount", "payment_date", "modification"]
    order_columns = columns
    max_display_length = 500
    date_template = get_template("core/_date_column.html")
    modification_template = Template("""<a href="{% url 'expense.views.expense_payments' record.id %}"><img src='{{MEDIA_URL}}img/icon_changelink.gif'/>""")

    def get_initial_queryset(self):
        return ExpensePayment.objects.all()

    def filter_queryset(self, qs):
        """ simple search on some attributes"""
        search = self.request.GET.get(u'search[value]', None)
        if search:
            qs = qs.filter(Q(expense__comment__icontains=search) |
                           Q(expense__description__icontains=search) |
                           Q(expense__user__first_name__icontains=search) |
                           Q(expense__user__last_name__icontains=search) |
                           Q(expense__user__username=search) |
                           Q(expense__lead__client__organisation__company__name__icontains=search) |
                           Q(expense__lead__client__organisation__name__iexact=search) |
                           Q(expense__lead__description__icontains=search) |
                           Q(expense__lead__deal_id__icontains=search))
            qs = qs.distinct()
        return qs

    def render_column(self, row, column):
        if column == "user":
            return link_to_consultant(row.user())
        elif column == "payment_date":
            return self.date_template.render({"date": row.payment_date})
        elif column == "amount":
            return to_int_or_round(row.amount(), 2)
        elif column == "modification":
            return self.modification_template.render(RequestContext(self.request, {"record": row}))
        else:
            return super(ExpensePaymentTableDT, self).render_column(row, column)

