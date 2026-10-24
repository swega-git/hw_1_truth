
# =============================================================================
# robot-models.py  --  LLM-generated data model for AttendanceChimp (HW3)
#
# LLM used : Claude (Anthropic), Claude Sonnet 5.5
#
# Prompt (verbatim):
#   "Design an improved Django ORM data model for AttendanceChimp. for the LLM
#    part of this assignemnt
#    Include InstructorProfile, StudentProfile, Course, Enrollment,
#    Lecture, and QRCodeUpload. Instructors teach courses, students
#    enroll in courses, lectures have QR-code identifiers, and students
#    upload QR-code images to record attendance. Use the code,the pdf with
#    more information and the ER diagram attached as .png to this chat to
#    include reasonable additional features for a practical attendance
#    management system,such as timestamps,constraints, QR-code expiration to
#    minimise cheating,and attendance verification. Use clear, standard Django code."
#
# Note: only the HW3 instructions PDF was actually visible to the LLM. The
# existing models.py and the ER-diagram .png were NOT attached, so this model
# was built from the PDF specification alone.
#
# Requires Django >= 5.1 (uses CheckConstraint(condition=...)).
# =============================================================================
"""
AttendanceChimp data model.

Entity overview
---------------
    auth.User (Django built-in)
        |-- 1:1 --> InstructorProfile --1:N--> Course
        |-- 1:1 --> StudentProfile ----N:M---> Course   (through Enrollment)

    Course --1:N--> Lecture (each lecture owns a QR token with a validity window)
    StudentProfile --1:N--> QRCodeUpload <--N:1-- Lecture (optional)

Why two profile tables instead of one "Users" table?
    Instructors and students have different attributes (department vs. student
    ID / graduation year) and different permissions. Authentication stays in
    Django's built-in User; the profiles hold only role-specific data. Keeping
    them separate also makes it impossible for a student to be set as a
    course's instructor by mistake (Course.instructor is an InstructorProfile).

Anti-cheating design
    * Every lecture has an unguessable random QR token (not a sequential ID).
    * The token is only valid inside [qr_valid_from, qr_expires_at]; the
      instructor can rotate it with Lecture.regenerate_qr().
    * Upload timestamps are set by the server (auto_now_add), never by the client.
    * Uploads are checked for: wrong token, expired token, student not
      enrolled, photo taken before the QR existed (EXIF), and the same image
      file being reused by several students (SHA-256 hash).
    * The database itself guarantees at most one VERIFIED upload per
      (student, lecture) and one VERIFIED upload per image per lecture.
"""

import hashlib
import os
import secrets
import uuid
from datetime import timedelta

from django.conf import settings
from django.core.validators import (
    FileExtensionValidator,
    MaxValueValidator,
    MinValueValidator,
)
from django.db import models
from django.db.models import F, Q
from django.utils import timezone

# How long a freshly created QR code stays valid, in minutes.
DEFAULT_QR_WINDOW_MINUTES = 15
# Photos taken more than this long before the QR existed are treated as stale.
EXIF_TOLERANCE = timedelta(minutes=1)


# ---------------------------------------------------------------------------
# Helper functions
# ---------------------------------------------------------------------------
def generate_qr_token():
    """Return a fresh, unguessable QR identifier (32 URL-safe characters)."""
    return secrets.token_urlsafe(24)


def qr_upload_path(instance, filename):
    """
    Store uploads at qr_uploads/lecture_<id>/student_<id>/<random>.<ext>.

    The original filename is discarded (random UUID) so students cannot
    overwrite each other's files or smuggle in odd path characters.
    """
    ext = os.path.splitext(filename)[1].lower()
    lecture_part = instance.lecture_id or "unmatched"
    return f"qr_uploads/lecture_{lecture_part}/student_{instance.student_id}/{uuid.uuid4().hex}{ext}"


class TimeStampedModel(models.Model):
    """Abstract base: adds created_at / updated_at to every table."""

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# ---------------------------------------------------------------------------
# People
# ---------------------------------------------------------------------------
class InstructorProfile(TimeStampedModel):
    """Role-specific data for an instructor. Login/identity lives in auth.User."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="instructor_profile",
    )
    department = models.CharField(max_length=100, blank=True)

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        return self.user.get_full_name() or self.user.get_username()


class StudentProfile(TimeStampedModel):
    """Role-specific data for a student. Login/identity lives in auth.User."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="student_profile",
    )
    student_id = models.CharField(
        max_length=20, unique=True, help_text="University-issued student ID."
    )
    graduation_year = models.PositiveSmallIntegerField(
        null=True,
        blank=True,
        validators=[MinValueValidator(1900), MaxValueValidator(2200)],
    )

    class Meta:
        ordering = ["user__last_name", "user__first_name"]

    def __str__(self):
        name = self.user.get_full_name() or self.user.get_username()
        return f"{name} ({self.student_id})"


# ---------------------------------------------------------------------------
# Courses and enrollment
# ---------------------------------------------------------------------------
class Course(TimeStampedModel):
    """
    One course offering in one term, taught by exactly one instructor.

    The weekly meeting schedule is stored as days + start/end time
    (e.g. "TuTh", 10:30-11:50). Individual meetings are Lecture rows.
    Students are linked through Enrollment (many-to-many with extra data).
    """

    code = models.CharField(max_length=20, help_text="e.g. DATA 13600")
    name = models.CharField(max_length=200)
    term = models.CharField(max_length=20, help_text="e.g. Fall 2026")
    instructor = models.ForeignKey(
        InstructorProfile,
        on_delete=models.PROTECT,  # don't silently delete courses with an instructor
        related_name="courses",
    )
    students = models.ManyToManyField(
        StudentProfile, through="Enrollment", related_name="courses"
    )

    meeting_days = models.CharField(max_length=20, help_text="e.g. MWF or TuTh")
    start_time = models.TimeField(help_text="Usual start time of a meeting.")
    end_time = models.TimeField(help_text="Usual end time of a meeting.")
    location = models.CharField(max_length=100, blank=True)

    start_date = models.DateField(help_text="First day of the term for this course.")
    end_date = models.DateField(help_text="Last day of the term for this course.")
    is_active = models.BooleanField(default=True)

    class Meta:
        ordering = ["-start_date", "code"]
        constraints = [
            models.UniqueConstraint(
                fields=["code", "term"], name="unique_course_code_per_term"
            ),
            models.CheckConstraint(
                condition=Q(end_time__gt=F("start_time")),
                name="course_end_time_after_start_time",
            ),
            models.CheckConstraint(
                condition=Q(end_date__gte=F("start_date")),
                name="course_end_date_not_before_start_date",
            ),
        ]

    def __str__(self):
        return f"{self.code} - {self.name} ({self.term})"

    def is_student_enrolled(self, student):
        """True if `student` is currently (actively) enrolled in this course."""
        return self.enrollments.filter(
            student=student, status=Enrollment.Status.ACTIVE
        ).exists()


class Enrollment(TimeStampedModel):
    """
    Join table linking a StudentProfile to a Course (many-to-many).

    Also stores enrollment status so a dropped student keeps their history
    but can no longer record attendance.
    """

    class Status(models.TextChoices):
        ACTIVE = "active", "Active"
        DROPPED = "dropped", "Dropped"

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="enrollments"
    )
    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="enrollments"
    )
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.ACTIVE
    )
    enrolled_at = models.DateTimeField(default=timezone.now)
    dropped_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["course", "student"]
        constraints = [
            models.UniqueConstraint(
                fields=["student", "course"], name="unique_enrollment_per_student_course"
            ),
        ]

    def __str__(self):
        return f"{self.student} in {self.course} [{self.status}]"

    # -- attendance analytics helpers --------------------------------------
    def lectures_held(self):
        """Number of non-cancelled lectures of this course that have started."""
        return self.course.lectures.filter(
            starts_at__lte=timezone.now(), is_cancelled=False
        ).count()

    def lectures_attended(self):
        """Number of held lectures with a VERIFIED QR upload from this student."""
        return QRCodeUpload.objects.filter(
            student=self.student,
            lecture__course=self.course,
            lecture__is_cancelled=False,
            lecture__starts_at__lte=timezone.now(),
            status=QRCodeUpload.Status.VERIFIED,
        ).count()  # at most one verified upload per (student, lecture)

    def attendance_rate(self):
        """Fraction in [0, 1] of held lectures attended (None if none held yet)."""
        held = self.lectures_held()
        return self.lectures_attended() / held if held else None


# ---------------------------------------------------------------------------
# Lectures and QR codes
# ---------------------------------------------------------------------------
class Lecture(TimeStampedModel):
    """
    A single class meeting. Each lecture owns a random QR token that students
    photograph and upload; the token is only valid during a time window.
    """

    course = models.ForeignKey(
        Course, on_delete=models.CASCADE, related_name="lectures"
    )
    title = models.CharField(max_length=200, blank=True)
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    is_cancelled = models.BooleanField(default=False)

    # QR identifier + validity window (anti-cheating).
    qr_token = models.CharField(
        max_length=64,
        unique=True,
        default=generate_qr_token,
        editable=False,
        help_text="Random secret encoded in this lecture's QR code.",
    )
    # Left blank on creation: save() defaults them to starts_at and
    # starts_at + DEFAULT_QR_WINDOW_MINUTES.
    qr_valid_from = models.DateTimeField(blank=True)
    qr_expires_at = models.DateTimeField(blank=True)

    class Meta:
        ordering = ["course", "starts_at"]
        constraints = [
            models.UniqueConstraint(
                fields=["course", "starts_at"], name="unique_lecture_start_per_course"
            ),
            models.CheckConstraint(
                condition=Q(ends_at__gt=F("starts_at")),
                name="lecture_ends_after_it_starts",
            ),
            models.CheckConstraint(
                condition=Q(qr_expires_at__gt=F("qr_valid_from")),
                name="lecture_qr_expires_after_valid_from",
            ),
        ]
        indexes = [models.Index(fields=["course", "starts_at"])]

    def __str__(self):
        return f"{self.course.code} lecture on {self.date}"

    def save(self, *args, **kwargs):
        if self.qr_valid_from is None:
            self.qr_valid_from = self.starts_at
        if self.qr_expires_at is None:
            self.qr_expires_at = self.qr_valid_from + timedelta(
                minutes=DEFAULT_QR_WINDOW_MINUTES
            )
        super().save(*args, **kwargs)

    @property
    def date(self):
        """Calendar date of the lecture (in the current time zone)."""
        return timezone.localtime(self.starts_at).date()

    @property
    def qr_payload(self):
        """The exact string that should be encoded into the QR image."""
        return f"attendancechimp:{self.qr_token}"

    def qr_is_active(self, at=None):
        """True if the QR code may be used at time `at` (default: now)."""
        at = at or timezone.now()
        return not self.is_cancelled and self.qr_valid_from <= at <= self.qr_expires_at

    def regenerate_qr(self, minutes=DEFAULT_QR_WINDOW_MINUTES):
        """
        Issue a brand-new token valid from now for `minutes` minutes.

        Use this to rotate the code mid-lecture (e.g. if a photo of the
        projector leaks). Pending uploads that carry the old token will fail
        verification; already-VERIFIED uploads are unaffected.
        """
        now = timezone.now()
        self.qr_token = generate_qr_token()
        self.qr_valid_from = now
        self.qr_expires_at = now + timedelta(minutes=minutes)
        self.save(
            update_fields=["qr_token", "qr_valid_from", "qr_expires_at", "updated_at"]
        )


class QRCodeUpload(TimeStampedModel):
    """
    A photo of a lecture's QR code uploaded by a student to record attendance.

    Lifecycle: PENDING -> VERIFIED or REJECTED (see verify()). The lecture is
    optional so that an upload whose QR could not be matched to any lecture is
    still stored for auditing (it can never become VERIFIED, see constraints).
    """

    class Status(models.TextChoices):
        PENDING = "pending", "Pending"
        VERIFIED = "verified", "Verified"
        REJECTED = "rejected", "Rejected"

    class RejectionReason(models.TextChoices):
        UNREADABLE = "unreadable", "QR code could not be read"
        WRONG_TOKEN = "wrong_token", "QR token does not match the lecture"
        EXPIRED = "expired", "Uploaded outside the QR validity window"
        NOT_ENROLLED = "not_enrolled", "Student is not enrolled in the course"
        STALE_PHOTO = "stale_photo", "Photo was taken before the QR code existed"
        DUPLICATE_IMAGE = "duplicate_image", "Same image already used for this lecture"
        OTHER = "other", "Other (see notes)"

    student = models.ForeignKey(
        StudentProfile, on_delete=models.CASCADE, related_name="qr_uploads"
    )
    lecture = models.ForeignKey(
        Lecture,
        on_delete=models.SET_NULL,  # keep the audit trail if a lecture is deleted
        null=True,
        blank=True,
        related_name="uploads",
    )
    image = models.FileField(
        upload_to=qr_upload_path,
        validators=[FileExtensionValidator(["jpg", "jpeg", "png", "heic", "webp"])],
        help_text="Photo of the QR code. (Swap for ImageField if Pillow is installed.)",
    )
    uploaded_at = models.DateTimeField(auto_now_add=True)  # server clock, not client

    # Data extracted from the upload (filled in by the processing code).
    decoded_token = models.CharField(max_length=64, blank=True)
    image_sha256 = models.CharField(max_length=64, blank=True, db_index=True)
    exif_taken_at = models.DateTimeField(
        null=True, blank=True, help_text="Capture time from EXIF metadata, if any."
    )
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    # Verification outcome.
    status = models.CharField(
        max_length=10, choices=Status.choices, default=Status.PENDING, db_index=True
    )
    rejection_reason = models.CharField(
        max_length=20, choices=RejectionReason.choices, blank=True
    )
    reviewed_at = models.DateTimeField(null=True, blank=True)
    reviewed_by = models.ForeignKey(
        InstructorProfile,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="reviewed_uploads",
        help_text="Empty when the decision was made automatically.",
    )
    notes = models.TextField(blank=True)

    class Meta:
        ordering = ["-uploaded_at"]
        constraints = [
            # A student can be marked present at most once per lecture.
            models.UniqueConstraint(
                fields=["student", "lecture"],
                condition=Q(status="verified"),
                name="one_verified_upload_per_student_per_lecture",
            ),
            # The same image file cannot verify two different students.
            models.UniqueConstraint(
                fields=["lecture", "image_sha256"],
                condition=Q(status="verified") & ~Q(image_sha256=""),
                name="one_verified_use_per_image_per_lecture",
            ),
            # Attendance can only be verified against an actual lecture.
            models.CheckConstraint(
                condition=~Q(status="verified") | Q(lecture__isnull=False),
                name="verified_upload_requires_lecture",
            ),
        ]
        indexes = [models.Index(fields=["lecture", "status"])]

    def __str__(self):
        return f"{self.student} -> {self.lecture or 'unmatched'} [{self.status}]"

    def save(self, *args, **kwargs):
        if self.image and not self.image_sha256:
            self.image_sha256 = self.compute_image_hash()
        super().save(*args, **kwargs)

    def compute_image_hash(self):
        """SHA-256 hex digest of the uploaded file (detects re-used photos)."""
        digest = hashlib.sha256()
        for chunk in self.image.chunks():
            digest.update(chunk)
        return digest.hexdigest()

    # -- verification -------------------------------------------------------
    def find_problem(self):
        """
        Return a RejectionReason value if this upload fails any check,
        or None if it passes all of them. Does not modify or save anything.
        """
        lecture = self.lecture
        if not self.decoded_token:
            return self.RejectionReason.UNREADABLE
        if lecture is None or not secrets.compare_digest(
            self.decoded_token.encode(), lecture.qr_token.encode()
        ):
            return self.RejectionReason.WRONG_TOKEN
        if not lecture.course.is_student_enrolled(self.student):
            return self.RejectionReason.NOT_ENROLLED
        when = self.uploaded_at or timezone.now()
        if not lecture.qr_is_active(when):
            return self.RejectionReason.EXPIRED
        if self.exif_taken_at and self.exif_taken_at < lecture.qr_valid_from - EXIF_TOLERANCE:
            return self.RejectionReason.STALE_PHOTO
        if (
            self.image_sha256
            and QRCodeUpload.objects.filter(
                lecture=lecture,
                image_sha256=self.image_sha256,
                status=self.Status.VERIFIED,
            )
            .exclude(pk=self.pk)
            .exists()
        ):
            return self.RejectionReason.DUPLICATE_IMAGE
        return None

    def verify(self, reviewed_by=None):
        """
        Run the automatic checks and record the outcome.

        Pass an InstructorProfile as `reviewed_by` for a manual review;
        leave it None for automatic verification.
        """
        problem = self.find_problem()
        self.status = self.Status.REJECTED if problem else self.Status.VERIFIED
        self.rejection_reason = problem or ""
        self.reviewed_at = timezone.now()
        self.reviewed_by = reviewed_by
        self.save()
        return self.status == self.Status.VERIFIED

