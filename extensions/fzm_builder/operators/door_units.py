"""Resolve the single, existing wall cutter behind a door's display objects."""

DOOR = 'IS_ENTRY_DOOR_BP'
PART_FLAGS = (
    'FZM_HINGED_3D_VISUAL', 'FZM_NATIVE_DOOR_VISUAL', 'FZM_DOOR_CASING',
    'FZM_DOOR_SWING', 'IS_2D_ANNOTATION',
)
FIXED = (True, True, True)


def local(obj):
    return obj and not (obj.library or obj.override_library)


def cage_for(obj):
    """Recognize generated display parts, not arbitrary scene children."""
    if obj and obj.get(DOOR):
        return obj
    if obj and obj.parent and obj.parent.get(DOOR) and any(obj.get(key) for key in PART_FLAGS):
        return obj.parent
    return None


def protect_part(obj):
    if not local(obj) or cage_for(obj) in (None, obj):
        return
    obj.lock_location = obj.lock_rotation = obj.lock_scale = FIXED
    if obj.get('FZM_DOOR_CASING'):
        # Casing used to be skipped by picking. It is now a valid handle,
        # but cannot be transformed independently through Blender's own tools.
        obj.hide_select = False


def protect(cage):
    if not local(cage) or not cage.get(DOOR):
        return
    # Free Blender transforms, including a standard Move gizmo in an old
    # workspace, must not bypass the host-wall interval. Our operator and
    # Edit Door can still update the cage directly.
    cage.lock_location = cage.lock_rotation = cage.lock_scale = FIXED
    for obj in cage.children:
        protect_part(obj)


def protect_saved_doors(objects):
    for obj in objects:
        if obj.get(DOOR):
            protect(obj)
