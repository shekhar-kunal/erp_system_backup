from django.shortcuts import render

# Create your views here.
from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from rest_framework.views import APIView
from django.db.models import Sum, Q
from django.utils import timezone
from datetime import timedelta
from decimal import Decimal
from .models import Account, JournalEntry, JournalLine, ExchangeRate, FiscalYear, FiscalPeriod
from .serializers import (
    AccountSerializer, JournalEntrySerializer, ExchangeRateSerializer,
    TrialBalanceSerializer
)


class AccountViewSet(viewsets.ModelViewSet):
    queryset = Account.objects.filter(is_active=True)
    serializer_class = AccountSerializer
    
    @action(detail=True, methods=['get'])
    def balance_at_date(self, request, pk=None):
        account = self.get_object()
        date = request.query_params.get('date', timezone.now().date())
        balance = account.balance_at_date(date)
        return Response({'balance': balance})


class JournalEntryViewSet(viewsets.ModelViewSet):
    queryset = JournalEntry.objects.all()
    serializer_class = JournalEntrySerializer
    
    @action(detail=True, methods=['post'])
    def post_entry(self, request, pk=None):
        entry = self.get_object()
        try:
            entry.post(request.user)
            return Response({'status': 'posted'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
    
    @action(detail=True, methods=['post'])
    def approve(self, request, pk=None):
        entry = self.get_object()
        try:
            entry.approve(request.user)
            return Response({'status': 'approved'})
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ExchangeRateViewSet(viewsets.ModelViewSet):
    queryset = ExchangeRate.objects.all()
    serializer_class = ExchangeRateSerializer
    
    @action(detail=False, methods=['get'])
    def latest(self, request):
        from_currency = request.query_params.get('from', 'USD')
        to_currency = request.query_params.get('to', 'EUR')
        
        rate = ExchangeRate.objects.filter(
            from_currency=from_currency,
            to_currency=to_currency
        ).order_by('-date').first()
        
        if rate:
            serializer = self.get_serializer(rate)
            return Response(serializer.data)
        return Response({'error': 'Rate not found'}, status=status.HTTP_404_NOT_FOUND)


class TrialBalanceView(APIView):
    def get(self, request):
        date = request.query_params.get('date', timezone.now().date())
        
        accounts = Account.objects.filter(is_active=True)
        data = []
        
        for account in accounts:
            debits = JournalLine.objects.filter(
                account=account,
                debit_credit='debit',
                journal_entry__entry_date__lte=date,
                journal_entry__is_posted=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            credits = JournalLine.objects.filter(
                account=account,
                debit_credit='credit',
                journal_entry__entry_date__lte=date,
                journal_entry__is_posted=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            balance = account.opening_balance
            if account.normal_balance == 'debit':
                balance += debits - credits
            else:
                balance += credits - debits
            
            data.append({
                'account_code': account.code,
                'account_name': account.name,
                'account_type': account.type,
                'debits': debits,
                'credits': credits,
                'balance': balance
            })
        
        serializer = TrialBalanceSerializer(data, many=True)
        return Response(serializer.data)


class ProfitLossView(APIView):
    def get(self, request):
        start_date = request.query_params.get('start_date')
        end_date = request.query_params.get('end_date')
        
        if not start_date or not end_date:
            today = timezone.now().date()
            start_date = today.replace(day=1)
            end_date = today
        
        # Get income accounts
        income_accounts = Account.objects.filter(type='income', is_active=True)
        income_data = []
        total_income = Decimal('0')
        
        for account in income_accounts:
            credits = JournalLine.objects.filter(
                account=account,
                debit_credit='credit',
                journal_entry__entry_date__range=[start_date, end_date],
                journal_entry__is_posted=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            debits = JournalLine.objects.filter(
                account=account,
                debit_credit='debit',
                journal_entry__entry_date__range=[start_date, end_date],
                journal_entry__is_posted=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            balance = credits - debits
            income_data.append({
                'account_code': account.code,
                'account_name': account.name,
                'amount': balance
            })
            total_income += balance
        
        # Get expense accounts
        expense_accounts = Account.objects.filter(type='expense', is_active=True)
        expense_data = []
        total_expenses = Decimal('0')
        
        for account in expense_accounts:
            debits = JournalLine.objects.filter(
                account=account,
                debit_credit='debit',
                journal_entry__entry_date__range=[start_date, end_date],
                journal_entry__is_posted=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            credits = JournalLine.objects.filter(
                account=account,
                debit_credit='credit',
                journal_entry__entry_date__range=[start_date, end_date],
                journal_entry__is_posted=True
            ).aggregate(total=Sum('amount'))['total'] or 0
            
            balance = debits - credits
            expense_data.append({
                'account_code': account.code,
                'account_name': account.name,
                'amount': balance
            })
            total_expenses += balance
        
        return Response({
            'period': {
                'start_date': start_date,
                'end_date': end_date
            },
            'income': {
                'accounts': income_data,
                'total': total_income
            },
            'expenses': {
                'accounts': expense_data,
                'total': total_expenses
            },
            'net_profit': total_income - total_expenses
        })


class BalanceSheetView(APIView):
    def get(self, request):
        as_at_date = request.query_params.get('as_at_date', timezone.now().date())
        
        # Get assets
        assets = Account.objects.filter(type='asset', is_active=True)
        asset_data = []
        total_assets = Decimal('0')
        
        for account in assets:
            balance = account.balance_at_date(as_at_date)
            asset_data.append({
                'account_code': account.code,
                'account_name': account.name,
                'balance': balance
            })
            total_assets += balance
        
        # Get liabilities
        liabilities = Account.objects.filter(type='liability', is_active=True)
        liability_data = []
        total_liabilities = Decimal('0')
        
        for account in liabilities:
            balance = account.balance_at_date(as_at_date)
            liability_data.append({
                'account_code': account.code,
                'account_name': account.name,
                'balance': balance
            })
            total_liabilities += balance
        
        # Get equity
        equity = Account.objects.filter(type='equity', is_active=True)
        equity_data = []
        total_equity = Decimal('0')
        
        for account in equity:
            balance = account.balance_at_date(as_at_date)
            equity_data.append({
                'account_code': account.code,
                'account_name': account.name,
                'balance': balance
            })
            total_equity += balance
        
        return Response({
            'as_at_date': as_at_date,
            'assets': {
                'accounts': asset_data,
                'total': total_assets
            },
            'liabilities': {
                'accounts': liability_data,
                'total': total_liabilities
            },
            'equity': {
                'accounts': equity_data,
                'total': total_equity
            },
            'total_liabilities_equity': total_liabilities + total_equity
        })


class AgingReportView(APIView):
    def get(self, request):
        from .models import Invoice, Bill
        
        # from_days inclusive, to_days inclusive (None = unbounded past)
        aging_buckets = [
            {'name': '0-30 days',    'from_days': 0,  'to_days': 30},
            {'name': '31-60 days',   'from_days': 31, 'to_days': 60},
            {'name': '61-90 days',   'from_days': 61, 'to_days': 90},
            {'name': 'Over 90 days', 'from_days': 91, 'to_days': None},
        ]

        today = timezone.now().date()

        def filter_by_bucket(qs, bucket):
            if bucket['to_days'] is None:
                return qs.filter(due_date__lte=today - timedelta(days=bucket['from_days']))
            return qs.filter(
                due_date__gte=today - timedelta(days=bucket['to_days']),
                due_date__lte=today - timedelta(days=bucket['from_days']),
            )

        # Accounts Receivable Aging
        ar_invoices = Invoice.objects.filter(
            status__in=['sent', 'partial'],
            due_date__lt=today
        )

        ar_aging = []
        for bucket in aging_buckets:
            invoices = filter_by_bucket(ar_invoices, bucket)
            total = sum(inv.balance_due for inv in invoices)
            ar_aging.append({
                'bucket': bucket['name'],
                'total': total,
                'count': invoices.count()
            })

        # Accounts Payable Aging
        ap_bills = Bill.objects.filter(
            status__in=['received', 'partial'],
            due_date__lt=today
        )

        ap_aging = []
        for bucket in aging_buckets:
            bills = filter_by_bucket(ap_bills, bucket)
            
            total = sum(bill.balance_due for bill in bills)
            ap_aging.append({
                'bucket': bucket['name'],
                'total': total,
                'count': bills.count()
            })
        
        return Response({
            'as_at_date': today,
            'accounts_receivable': ar_aging,
            'accounts_payable': ap_aging,
            'total_ar': sum(b['total'] for b in ar_aging),
            'total_ap': sum(b['total'] for b in ap_aging)
        })


class CashFlowView(APIView):
    def get(self, request):
        period = request.query_params.get('period', 'monthly')  # daily, weekly, monthly
        months = int(request.query_params.get('months', 6))
        
        end_date = timezone.now().date()
        start_date = end_date - timedelta(days=30 * months)
        
        # Get cash accounts
        cash_accounts = Account.objects.filter(
            code__startswith='10',  # Cash accounts start with 10
            is_active=True
        )
        
        # Get all journal lines for cash accounts in period
        cash_lines = JournalLine.objects.filter(
            account__in=cash_accounts,
            journal_entry__entry_date__range=[start_date, end_date],
            journal_entry__is_posted=True
        ).select_related('journal_entry')
        
        # Group by date
        from collections import defaultdict
        daily_cash = defaultdict(lambda: {'inflow': 0, 'outflow': 0})
        
        for line in cash_lines:
            date = line.journal_entry.entry_date
            if line.debit_credit == 'debit':
                daily_cash[date]['inflow'] += line.amount
            else:
                daily_cash[date]['outflow'] += line.amount
        
        # Format response
        data = []
        current_date = start_date
        while current_date <= end_date:
            day_data = daily_cash.get(current_date, {'inflow': 0, 'outflow': 0})
            data.append({
                'date': current_date,
                'inflow': day_data['inflow'],
                'outflow': day_data['outflow'],
                'net': day_data['inflow'] - day_data['outflow']
            })
            current_date += timedelta(days=1)
        
        return Response({
            'period': period,
            'start_date': start_date,
            'end_date': end_date,
            'data': data
        })