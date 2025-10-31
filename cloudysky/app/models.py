# Design goals:
#  Users/Roles, Posts, Comments, Avatars, Media.

from __future__ import annotations

from django.contrib.auth import get_user_model
from django.core.validators import FileExtensionValidator
from django.db import models
from django.utils import timezone

User = get_user_model()


# ---- Users & Roles ---------------------------------------------------------

class UserType(models.Model):
    """Track whether a user is a 'serf' or an 'administrator'."""
    SERF = "serf"
    ADMIN = "admin"
    ROLE_CHOICES = [(SERF, "Serf"), (ADMIN, "Administrator")]

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="usertype")
    role = models.CharField(max_length=16, choices=ROLE_CHOICES, default=SERF)

    def __str__(self) -> str:
        return f"{self.user.username} ({self.role})"


class UserProfile(models.Model):
    """Public user page data (just a bio for simplicity)."""
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    bio = models.TextField(blank=True)
    created_at = models.DateTimeField(default=timezone.now)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self) -> str:
        return f"Profile<{self.user.username}>"


# ---- Moderation helpers (simple choices, no extra table) -------------------

SUPPRESSION_REASON_CHOICES = [
    ("spam", "Spam or promotional"),
    ("off_topic", "Off-topic"),
    ("incivility", "Incivility/harassment"),
    ("policy", "Policy violation"),
    ("other", "Other"),
]


# ---- Core: Posts & Comments -----------------------------------------------

class Post(models.Model):
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="posts")
    body = models.TextField()
    body_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Moderation flags (denormalized)
    is_suppressed = models.BooleanField(default=False, db_index=True)
    suppressed_at = models.DateTimeField(null=True, blank=True)
    suppressed_reason = models.CharField(
        max_length=32, choices=SUPPRESSION_REASON_CHOICES, blank=True, default=""
    )
    suppressed_message_to_author = models.TextField(blank=True)

    class Meta:
        ordering = ["-created_at"]

    def save(self, *args, **kwargs):
        self.body_bytes = len(self.body.encode("utf-8")) if self.body else 0
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Post#{self.id} by {self.author}"


class Comment(models.Model):
    post = models.ForeignKey(Post, on_delete=models.CASCADE, related_name="comments")
    author = models.ForeignKey(User, on_delete=models.CASCADE, related_name="comments")
    body = models.TextField()
    body_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now, db_index=True)

    # Moderation flags (denormalized)
    is_suppressed = models.BooleanField(default=False, db_index=True)
    suppressed_at = models.DateTimeField(null=True, blank=True)
    suppressed_reason = models.CharField(
        max_length=32, choices=SUPPRESSION_REASON_CHOICES, blank=True, default=""
    )
    suppressed_message_to_author = models.TextField(blank=True)

    class Meta:
        ordering = ["created_at"]

    def save(self, *args, **kwargs):
        self.body_bytes = len(self.body.encode("utf-8")) if self.body else 0
        super().save(*args, **kwargs)

    def __str__(self) -> str:
        return f"Comment#{self.id} by {self.author} on Post#{self.post_id}"


# ---- Avatars ---------------------------------------------------------------

def avatar_upload_path(instance: "Avatar", filename: str) -> str:
    ts = timezone.now().strftime("%Y%m%d_%H%M%S")
    return f"avatars/user_{instance.user_id}/{ts}_{filename}"


class Avatar(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="avatars")
    image = models.ImageField(
        upload_to=avatar_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"])],
    )
    is_active = models.BooleanField(default=True)
    image_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    class Meta:
        indexes = [models.Index(fields=["user", "is_active"])]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            self.image_bytes = self.image.size or 0
        except Exception:
            self.image_bytes = 0
        super().save(update_fields=["image_bytes"])

    def __str__(self) -> str:
        return f"Avatar#{self.id} for {self.user} (active={self.is_active})"


# ---- Media (images attached to posts or comments) --------------------------

def media_upload_path(instance: "Media", filename: str) -> str:
    ts = timezone.now().strftime("%Y%m%d_%H%M%S")
    target = f"post_{instance.post_id}" if instance.post_id else f"comment_{instance.comment_id}" if instance.comment_id else "orphan"
    return f"media/{target}/{ts}_{filename}"


class Media(models.Model):
    """Image uploads attached to either a Post or a Comment (but not both)."""
    uploader = models.ForeignKey(User, on_delete=models.CASCADE, related_name="media")
    file = models.FileField(
        upload_to=media_upload_path,
        validators=[FileExtensionValidator(allowed_extensions=["jpg", "jpeg", "png", "gif", "webp"])],
    )
    file_bytes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(default=timezone.now)

    # Exactly one of these should be set:
    post = models.ForeignKey(Post, null=True, blank=True, on_delete=models.CASCADE, related_name="media")
    comment = models.ForeignKey(Comment, null=True, blank=True, on_delete=models.CASCADE, related_name="media")

    class Meta:
        constraints = [
            # XOR: link to a post OR a comment, but not both / neither
            models.CheckConstraint(
                name="media_exactly_one_target",
                check=(
                    (models.Q(post__isnull=False) & models.Q(comment__isnull=True)) |
                    (models.Q(post__isnull=True) & models.Q(comment__isnull=False))
                ),
            )
        ]
        indexes = [
            models.Index(fields=["uploader", "created_at"]),
            models.Index(fields=["post"]),
            models.Index(fields=["comment"]),
        ]

    def save(self, *args, **kwargs):
        super().save(*args, **kwargs)
        try:
            self.file_bytes = self.file.size or 0
        except Exception:
            self.file_bytes = 0
        super().save(update_fields=["file_bytes"])

    def __str__(self) -> str:
        tgt = f"post={self.post_id}" if self.post_id else f"comment={self.comment_id}"
        return f"Media#{self.id} ({tgt})"
