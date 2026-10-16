import hashlib,json

def load_profile(wire, pin):
    if hashlib.sha256(wire).hexdigest() != pin:
        raise ValueError('profile digest mismatch')
    return json.loads(wire)

def verify_image(profile, image, labels):
    if image != profile['image'] or labels != profile['image_labels']:
        raise ValueError('exact pinned image metadata mismatch')

def container_labels(profile, task):
    if set(task) != {'nbsr.campaign','nbsr.run','nbsr.role'}:
        raise ValueError('exact task ownership required')
    return {**profile['container_inherited_labels'], **task}
