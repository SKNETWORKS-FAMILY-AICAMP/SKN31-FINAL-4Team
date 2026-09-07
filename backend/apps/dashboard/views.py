from django.shortcuts import render


def home(request):
    return render(request, "dashboard/index.html")


def collection(request):
    return render(request, "dashboard/collection/index.html")


def data(request):
    return render(request, "dashboard/data/index.html")


def content(request):
    return render(request, "dashboard/content/index.html")


def analysis(request):
    return render(request, "dashboard/analysis/index.html")


def quality(request):
    return render(request, "dashboard/quality/index.html")


def import_data(request):
    return render(request, "dashboard/tools/import.html")


def export_data(request):
    return render(request, "dashboard/tools/export.html")


def probe(request):
    return render(request, "dashboard/tools/probe.html")


def api_settings(request):
    return render(request, "dashboard/settings/api.html")


def collection_settings(request):
    return render(
        request,
        "dashboard/settings/collection.html",
    )