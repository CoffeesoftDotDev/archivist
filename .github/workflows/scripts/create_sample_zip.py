import zipfile


with zipfile.ZipFile("photos/album.zip", "w") as archive:
    archive.writestr("a.jpg", "x")
