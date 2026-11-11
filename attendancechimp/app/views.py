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
from uuid import uuid4
from django.utils import timezone

from .models import StudentProfile, InstructorProfile, Course, Lecture, QRCodeUpload
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
def new_course(request):
    return render(request, "app/new_course.html")

@csrf_exempt
def createCourse(request):
    # Check that the user is logged in.
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    # Check that the logged-in user is an instructor.
    instructor = InstructorProfile.objects.filter(user=request.user).first()
    if instructor is None:
        return HttpResponse(status=401)

    # Only POST requests can create a course.
    if request.method != "POST":
        return HttpResponse(status=405)

    name = request.POST.get("course-name", "").strip()
    start_time = request.POST.get("start-time", "")
    end_time = request.POST.get("end-time", "")

    days = []
    for day in ("mon", "tue", "wed", "thu", "fri"):
        field_name = "day-" + day
        if field_name in request.POST:
            days.append(day.title())

    if not name or not start_time or not end_time or not days:
        return HttpResponseBadRequest("Course name, times, and meeting days are required")

    if Course.objects.filter(name=name).exists():
        return HttpResponseBadRequest("Course names must be unique")

    day_text = ", ".join(days)
    schedule = f"{day_text} {start_time}-{end_time}"

    Course.objects.create(
        name=name,
        instructor=instructor,
        meeting_schedule=schedule,
    )
    return HttpResponse(status=200)

def new_lecture(request):
    courses = Course.objects.all()
    return render(request, "app/new_lecture.html", {"courses": courses})

@csrf_exempt
def createLecture(request):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    if not InstructorProfile.objects.filter(user=request.user).exists():
        return HttpResponse(status=401)

    if request.method != "POST":
        return HttpResponse(status=405)

    course_name = request.POST.get("choice", "")
    course = Course.objects.filter(name=course_name).first()
    if course is None:
        return HttpResponseBadRequest("Choose an existing course")

    Lecture.objects.create(
        course=course,
        date=timezone.localdate(),
        qr_identifier=uuid4().hex,
    )
    return HttpResponse(status=200)


def new_qr_upload(request):
    return render(request, "app/new_qr_upload.html")


@csrf_exempt
def createQRCodeUpload(request):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    student = StudentProfile.objects.filter(user=request.user).first()
    if student is None:
        return HttpResponse(status=401)

    if request.method != "POST":
        return HttpResponse(status=405)

    image = request.FILES.get("imageUpload")
    if image is None:
        return HttpResponseBadRequest("Choose an image")

    QRCodeUpload.objects.create(
        student=student,
        image=image,
    )
    return HttpResponse(status=200)

def dumpUploads(request):
    if not request.user.is_authenticated:
        return HttpResponse(status=401)

    if not InstructorProfile.objects.filter(user=request.user).exists():
        return HttpResponse(status=401)

    if request.method != "GET":
        return HttpResponse(status=405)

    data = []

    for upload in QRCodeUpload.objects.select_related("student__user"):
        data.append({
            "username": upload.student.user.username,
            "upload_time": timezone.localtime(upload.uploaded_at).strftime(
                "%Y-%m-%d %H:%M:%S"
            ),
        })

    return JsonResponse(data, safe=False)


# ---------------------------------------------------------------------------
# HW6  — getUploads
# ---------------------------------------------------------------------------



