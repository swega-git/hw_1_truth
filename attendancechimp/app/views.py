"""
views.py — HTTP request handlers for AttendanceChimp.

Each view corresponds to one URL endpoint.  Views receive an HTTP request,
interact with the database via models.py, and return an HTTP response.
"""

from django.shortcuts import render, redirect
from django.http import (HttpResponse, HttpResponseForbidden,
                         HttpResponseBadRequest, JsonResponse)
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth.models import User
from django.contrib.auth import authenticate, login
from datetime import datetime
import zoneinfo
import json
import io


from .models import StudentProfile, InstructorProfile
CDT = zoneinfo.ZoneInfo("America/Chicago")


# ---------------------------------------------------------------------------
# HW2  — index, time, sum
# ---------------------------------------------------------------------------

def index(request):
    """Render the home page (index.html)."""
    # Get the current Chicago time
    now = datetime.now(CDT)
    current_time = now.strftime("%H:%M")

    # Check whether the user is logged in
    if request.user.is_authenticated:
        username = request.user.username
    else:
        username = "Not logged in."

    # Store the information in a dictionary
    context = {
        "current_time": current_time,
        "username": username
    }

    # Display the HTML page
    return render(request, "app/index.html", context)

def time_view(request):
  chi_time_now = chi_time_now = datetime.now(CDT)
  formatted_time = chi_time_now.strftime("%H:%M")
  return HttpResponse(formatted_time)

def sum_view(request):
    n1 = float(request.GET.get("n1", 0))
    n2 = float(request.GET.get("n2", 0))

    total = n1 + n2

    return JsonResponse({"sum": total})






# ---------------------------------------------------------------------------
# HW4  — user creation
# ---------------------------------------------------------------------------

def new(request):
    if request.method == "GET":
        return render(request, "app/new.html")
    else:
        return HttpResponseBadRequest("Only GET allowed")


@csrf_exempt
def createUser(request):

    if request.method != "POST":
        return HttpResponseBadRequest("Only POST allowed")

    user_name = request.POST.get("user_name")
    email = request.POST.get("email")
    password = request.POST.get("password")
    is_student = request.POST.get("is_student")


    if User.objects.filter(email=email).exists():
        return HttpResponseBadRequest("Email already exists")

    user = User.objects.create_user(
    username=user_name,
    email=email,
    password=password)

    if is_student == "1":
        StudentProfile.objects.create(user=user)
    else:
        InstructorProfile.objects.create(user=user)

    login(request, user)

    return HttpResponse("User created successfully")


# ---------------------------------------------------------------------------
# HW5  — courses, lectures, QR uploads, dump
# ---------------------------------------------------------------------------



# ---------------------------------------------------------------------------
# HW6  — getUploads
# ---------------------------------------------------------------------------



