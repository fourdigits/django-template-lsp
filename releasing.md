# Releasing

To create a new release, follow these steps:

- Update the version number in `djslsp/__init__.py` and push this to `main`.
    - We use [semantic](https://semver.org/) versioning.
- Create a new tag and push the tag by push the tag using `git push --tags`.

The release will be automatically built and published to [PyPi](https://pypi.org/project/django-template-lsp/).

After publishing to PyPi, a draft release is automatically made on Github. 
Edit this release, include the changes in the "What's changed" section and publish the release.
