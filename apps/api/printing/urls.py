from django.urls import path

from .views import (
    AgentDetailView,
    AgentListCreateView,
    AgentPairView,
    AgentPollView,
    AgentPrintersView,
    AgentRegenerateCodeView,
    AutoPrintView,
    JobCompleteView,
    JobQueueView,
)

urlpatterns = [
    # User-facing (JWT auth)
    path("agents/", AgentListCreateView.as_view(), name="print-agents"),
    path("agents/<int:pk>/", AgentDetailView.as_view(), name="print-agent-detail"),
    path("agents/<int:pk>/regenerate-code/", AgentRegenerateCodeView.as_view(), name="print-agent-regen"),
    path("jobs/queue/", JobQueueView.as_view(), name="print-job-queue"),
    path("print/", AutoPrintView.as_view(), name="print-auto"),

    # Agent-facing (api_key auth)
    path("agents/pair/", AgentPairView.as_view(), name="print-agent-pair"),
    path("agents/poll/", AgentPollView.as_view(), name="print-agent-poll"),
    path("agents/printers/", AgentPrintersView.as_view(), name="print-agent-printers"),
    path("jobs/<int:pk>/complete/", JobCompleteView.as_view(), name="print-job-complete"),
]
