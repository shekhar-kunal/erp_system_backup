from django.urls import path, include
from rest_framework.routers import DefaultRouter
from . import views

router = DefaultRouter()
router.register(r'accounts', views.AccountViewSet)
router.register(r'journal-entries', views.JournalEntryViewSet)
router.register(r'exchange-rates', views.ExchangeRateViewSet)

urlpatterns = [
    path('api/', include(router.urls)),
    path('api/reports/trial-balance/', views.TrialBalanceView.as_view(), name='trial-balance'),
    path('api/reports/profit-loss/', views.ProfitLossView.as_view(), name='profit-loss'),
    path('api/reports/balance-sheet/', views.BalanceSheetView.as_view(), name='balance-sheet'),
    path('api/reports/cash-flow/', views.CashFlowView.as_view(), name='cash-flow'),
    path('api/reports/aging/', views.AgingReportView.as_view(), name='aging-report'),
]