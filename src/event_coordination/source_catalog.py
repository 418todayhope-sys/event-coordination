"""Reviewed identities disclosed by the stakeholder; importing never retrieves."""

from dataclasses import dataclass


@dataclass(frozen=True)
class Source:
    id: str
    role: str
    url: str
    disclosure_line: int
    publication_kind: str
    expected_type: str
    disclosure_override: str | None = None

    @property
    def disclosure_path(self) -> str:
        return self.disclosure_override or "interviews/project-c-event-coordination-20261016-1954.md"


SOURCES = (
    Source("attendee-signals", "attendee-signals", "https://docs.google.com/spreadsheets/d/1IXAEAFsZM6Q9IZZ_9pGqbFQ7l2ikr-oThqrEKudHwIU", 257, "fictional-exercise-record", "text/html"),
    Source("vendor-register", "vendor-record", "https://docs.google.com/spreadsheets/d/1cULbGrOQS-vuj862nV2EWND4oe0H5kf-smJ85VZegko", 203, "fictional-exercise-record", "text/html"),
    Source("budget-allocations", "budget", "https://docs.google.com/spreadsheets/d/1Cxo7CvcgImz9HbT8PThZyvaTuyd44ug7w5rBA1z5qlM", 540, "fictional-exercise-record", "text/html"),
    Source("calendar-constraints", "calendar", "https://docs.google.com/spreadsheets/d/1f_i6tUCHbJV-Ug_j6U3T4LEZ3yAr2ucdBnID-4C_-8s", 554, "fictional-exercise-record", "text/html"),
    Source("event-brief", "event-brief", "https://app.notion.com/p/3ba0b700541e81d0af55dc1a8f49f5af", 526, "fictional-exercise-record", "text/html"),
    Source("official-floor-plan", "floor-plan-or-image", "https://www.ticc.com.tw/wSite/public/Attachment/f1710485827023.pdf", 287, "real-publication", "application/pdf"),
    Source("official-accessibility", "venue-page", "https://www.ticc.com.tw/wSite/lp?ctNode=398&mp=2&xq_xCat=6", 288, "real-publication", "text/html"),
    Source("official-plenary-hall", "venue-page", "https://www.ticc.com.tw/wSite/sp?BaseDSD=7&CtUnit=99&ctNode=322&mp=2&roomId=PH&xdUrl=%2FwSite%2Fap%2Fcp_VenueSearch.jsp", 85, "real-publication", "text/html", "evidence/source-disclosures/project-c-assignment-c724104.md"),
)
LEGACY_SOURCE_IDS = frozenset(s.id for s in SOURCES if s.id != "official-plenary-hall")
CATALOG = {source.id: source for source in SOURCES}
