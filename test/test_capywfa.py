# SPDX-FileCopyrightText: 2019-2026 Siemens
# SPDX-FileCopyrightText: 2019-2026 Siemens Healthineers
#
# SPDX-License-Identifier: MIT

from capywfa.capywfa import pass3_download_sources, pass4_create_releases, pass6_link_releases
from capywfa.cdx_support import get_cdx, set_cdx
from capycli.bom.create_components import BomCreateComponents
from capycli.project.create_project import CreateProject
from capycli.common.map_result import MapResult
from capycli.common.capycli_bom_support import CaPyCliBom
from cyclonedx.model.bom import Bom
from cyclonedx.model.component import Component, ComponentType
from cyclonedx.model import ExternalReference, ExternalReferenceType, HashType, HashAlgorithm, XsUri
from packageurl import PackageURL

SHA1 = "f8ed764424ee04dac8298bdc1feed2e356f3d2cd"
FIXTURES = "test/fixtures"


def make_component(name="pkg", map_result=MapResult.FULL_MATCH_BY_ID,
                   source_check="passed"):
    comp = Component(
        name=name, type=ComponentType.LIBRARY,
        version="1.0", purl=PackageURL("deb", "debian", name, "1.0",
                                       {"arch": "source"}))
    set_cdx(comp, "MapResult", map_result)
    if source_check:
        set_cdx(comp, "Sw360SourceFileCheck", source_check)
    return comp


def make_bom(*components):
    return Bom(components=list(components))


def test_pass3_good_match_verified_gets_skip():
    """Good SW360 match with verified source → SourceFileDownload=skip, not missing."""
    bom = make_bom(make_component(map_result=MapResult.FULL_MATCH_BY_ID,
                                  source_check="passed"))
    bom, missing = pass3_download_sources(bom, "", "")
    assert get_cdx(bom.components[0], "SourceFileDownload") == "skip"
    assert missing == []


def test_pass3_no_match_no_source_goes_missing():
    """NO_MATCH with no local source → item in missing list, no SourceFileDownload set."""
    bom = make_bom(make_component(map_result=MapResult.NO_MATCH, source_check=""))
    bom, missing = pass3_download_sources(bom, "", "")
    assert get_cdx(bom.components[0], "SourceFileDownload") == ""
    assert len(missing) == 1
    assert missing[0].name == "pkg"


def test_pass3_no_match_with_valid_source_not_missing():
    """NO_MATCH but downloader provided a valid local source → not missing, not skip."""
    comp = make_component(map_result=MapResult.NO_MATCH, source_check="")
    comp.external_references.add(ExternalReference(
        type=ExternalReferenceType.DISTRIBUTION,
        comment=CaPyCliBom.SOURCE_FILE_COMMENT,
        url=XsUri(f"sources/{SHA1}/efibootguard-0.13.zip"),
        hashes={HashType(alg=HashAlgorithm.SHA_1, content=SHA1)},
    ))
    bom = make_bom(comp)
    # sbom_dir points at test/fixtures so the file is found at
    # test/fixtures/sources/<sha1>/efibootguard-0.13.zip
    bom, missing = pass3_download_sources(bom, FIXTURES, "")
    assert missing == []
    assert get_cdx(bom.components[0], "SourceFileDownload") != "failed"


def test_pass3_sources_downloaded_still_missing_gets_failed():
    """Re-entry with --sources-downloaded: item still missing → SourceFileDownload=failed."""
    bom = make_bom(make_component(map_result=MapResult.NO_MATCH, source_check=""))
    bom, missing = pass3_download_sources(bom, "", "", sources_downloaded=True)
    assert get_cdx(bom.components[0], "SourceFileDownload") == "failed"
    assert missing == []


def test_read_only_pass4_never_calls_create_items(monkeypatch, capsys):
    def fake_login(self, **kwargs):
        self.client = None
        return True

    def no_writes(self, bom):
        raise AssertionError("create_items called in read-only mode")

    monkeypatch.setattr(BomCreateComponents, "login", fake_login)
    monkeypatch.setattr(BomCreateComponents, "create_items", no_writes)
    bom = make_bom(make_component(map_result=MapResult.NO_MATCH, source_check=""))
    pass4_create_releases(bom, "https://sw360.example.com", "token", "", read_only=True)
    assert "would create or update: pkg 1.0" in capsys.readouterr().out


def test_read_only_pass6_never_updates_project(monkeypatch, tmp_path, capsys):
    class FakeClient:
        def get_project(self, project_id):
            return {"name": "demo", "version": "1"}

    def fake_login(self, **kwargs):
        self.client = FakeClient()
        return True

    def no_writes(self, *args, **kwargs):
        raise AssertionError("update_project called in read-only mode")

    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(CreateProject, "login", fake_login)
    monkeypatch.setattr(CreateProject, "update_project", no_writes)
    comp = make_component(map_result=MapResult.FULL_MATCH_BY_ID, source_check="passed")
    set_cdx(comp, "Sw360Id", "release-1")
    pass6_link_releases(make_bom(comp), "https://sw360.example.com", "token", "123", None,
                        read_only=True)
    assert "would link: pkg 1.0" in capsys.readouterr().out
