"""Tạo bộ câu hỏi tự nhiên nháp từ ground truth của benchmark định vị.

Bộ này phục vụ vòng biên soạn và duyệt độc lập. Không dùng các kết quả chạy trên
bộ nháp trong báo cáo chính thức trước khi người duyệt kiểm tra câu hỏi, đáp án,
citation và fact rubric.
"""

from __future__ import annotations

from copy import deepcopy
import csv
import json
from pathlib import Path


ROOT = Path(__file__).resolve().parent
SOURCE = ROOT / "questions.json"
OUTPUT = ROOT / "questions_natural_draft.json"
REVIEW_OUTPUT = ROOT / "natural_question_review_template.csv"


NATURAL_QUESTIONS = {
    "SINGLE_001": "Bộ Nội vụ có những nhiệm vụ và quyền hạn nào liên quan đến việc quản lý lao động Việt Nam trong hoạt động đầu tư ra nước ngoài?",
    "SINGLE_002": "Khi làm hồ sơ công bố mở cảng cạn, tổ chức hoặc cá nhân phải cung cấp giấy tờ gì để chứng minh quyền sử dụng đất?",
    "SINGLE_003": "Trong hồ sơ đề nghị Kiểm toán Nhà nước kiểm toán phần giảm doanh thu của dự án BOT đường bộ, cần có biên bản nào?",
    "SINGLE_004": "Tiền ký quỹ của doanh nghiệp bán hàng đa cấp được xử lý thế nào khi doanh nghiệp chấm dứt hoạt động nhưng không chấp hành quyết định xử phạt đã có hiệu lực?",
    "SINGLE_005": "Khu chế xuất được hiểu là gì?",
    "SINGLE_010": "Tổ chức tư vấn thiết kế có quyền yêu cầu chủ chương trình hoặc chủ đầu tư cung cấp những gì để thực hiện thiết kế dự án đầu tư công?",
    "SINGLE_012": "Khi quyết định chủ trương đầu tư chương trình hoặc dự án đầu tư công, yêu cầu về hiệu quả và phát triển bền vững được đặt ra như thế nào?",
    "SINGLE_013": "Những chủ thể nào của Quốc hội thực hiện giám sát hoạt động quản lý và đầu tư vốn nhà nước tại doanh nghiệp?",
    "SINGLE_014": "Ai có thẩm quyền xem xét, quyết định chủ trương dự án đầu tư ra nước ngoài của doanh nghiệp do Nhà nước nắm giữ toàn bộ vốn điều lệ?",
    "SINGLE_015": "Một cơ sở đăng kiểm xe cơ giới cần tối thiểu bao nhiêu đăng kiểm viên và lãnh đạo chuyên môn phải đáp ứng yêu cầu kinh nghiệm nào?",
    "SINGLE_017": "Nhà nước, xã hội và gia đình có trách nhiệm gì trong việc tạo điều kiện để phụ nữ phát triển và phát huy vai trò trong xã hội?",
    "SINGLE_018": "Vốn đầu tư công dùng để thanh toán cho doanh nghiệp dự án PPP theo hợp đồng BTL hoặc BLT được bố trí trong kế hoạch trung hạn và hằng năm như thế nào?",
    "SINGLE_019": "Nhà đầu tư có thể chịu hậu quả pháp lý gì nếu quá thời hạn mà chưa chuyển lợi nhuận từ hoạt động đầu tư ở nước ngoài về Việt Nam và không thực hiện thông báo?",
    "SINGLE_020": "Quy định hiện hành về cảng cạn điều chỉnh những hoạt động nào?",
    "SINGLE_021": "Sau khi Nhà nước chia sẻ phần giảm doanh thu của dự án BOT đường bộ, hợp đồng dự án và hợp đồng tín dụng cần được xử lý thế nào?",
    "SINGLE_022": "Hoạt động kinh doanh theo phương thức đa cấp được phép áp dụng đối với đối tượng nào?",
    "SINGLE_023": "Ai phải chịu chi phí giám định khi kết quả giám định làm tăng nghĩa vụ thuế đối với Nhà nước?",
    "SINGLE_025": "Cá nhân muốn đảm nhận chức danh giám đốc quản lý dự án đầu tư xây dựng phải đáp ứng yêu cầu chung nào về chuyên môn và kinh nghiệm?",
    "SINGLE_026": "Dự án mở rộng hoặc nâng cấp đường cao tốc đã được thỏa thuận với nhà đầu tư hiện hữu trước khi quy định mới có hiệu lực được chuyển tiếp như thế nào?",
    "SINGLE_028": "Chủ chương trình phải thực hiện những công việc nào khi chuẩn bị quyết định chủ trương đầu tư một chương trình đầu tư công?",
    "SINGLE_030": "Ai quyết định giao một địa phương làm cơ quan chủ quản đối với dự án đầu tư công triển khai trên địa bàn từ hai tỉnh trở lên?",
    "SINGLE_031": "Doanh nghiệp do Nhà nước nắm giữ toàn bộ vốn điều lệ phải tuân thủ nguyên tắc nào khi huy động vốn?",
    "SINGLE_033": "Khi một cơ sở đăng kiểm bị thu hồi giấy chứng nhận đủ điều kiện hoạt động, cơ quan nào chỉ định nơi tiếp nhận hồ sơ kiểm định được lưu trữ?",
    "SINGLE_035": "Ủy ban dự thảo Hiến pháp do cơ quan nào thành lập và ai quyết định thành phần, nhiệm vụ, quyền hạn của Ủy ban?",
    "SINGLE_036": "Đối với dự án PPP sử dụng nguồn chi thường xuyên để thanh toán, cơ quan nào thẩm định khả năng cân đối ngân sách?",
    "SINGLE_037": "Cơ quan nhà nước Việt Nam có trách nhiệm giải quyết tranh chấp giữa các nhà đầu tư trong quá trình đầu tư ra nước ngoài hay không?",
    "SINGLE_038": "Cảng cạn thực hiện những chức năng theo căn cứ pháp luật nào?",
    "SINGLE_039": "Khi xác định chi phí bồi thường do chấm dứt hợp đồng BOT giao thông trước thời hạn, lợi nhuận trên vốn chủ sở hữu của nhà đầu tư có được tính vào không?",
    "SINGLE_040": "Ai được xem là người tham gia bán hàng đa cấp?",
    "SINGLE_041": "Pháp luật bảo đảm tài sản hợp pháp của nhà đầu tư trước việc quốc hữu hóa hoặc tịch thu bằng biện pháp hành chính như thế nào?",
    "SINGLE_044": "Đối với quốc lộ hoặc đường cao tốc đã được giao cho địa phương quản lý trước khi quy định mới có hiệu lực, địa phương có tiếp tục thực hiện nhiệm vụ đã được giao không?",
    "SINGLE_045": "Trong cùng một giai đoạn quy hoạch, một dự án điện gió ngoài khơi bán điện lên hệ thống điện quốc gia được giao cho bao nhiêu đơn vị khảo sát?",
    "MULTI_001": "Nhà đầu tư phải chuyển lợi nhuận từ hoạt động đầu tư ở nước ngoài về Việt Nam trong thời hạn nào, và có được dùng lợi nhuận đó để hoán đổi nghĩa vụ với đối tác hay không?",
    "MULTI_002": "Công tác quản lý nhà nước về cảng cạn bao gồm việc quản lý giá, phí và việc thống kê dữ liệu như thế nào?",
    "MULTI_004": "Những hình thức phát triển mạng lưới bán hàng đa cấp nào bị xem là không dựa trên giao dịch mua bán hàng hóa?",
    "MULTI_007": "Dữ liệu nào trong cơ sở dữ liệu quy hoạch đô thị và nông thôn được công bố mở, và dữ liệu chủ của cơ sở dữ liệu này gồm những thành phần nào?",
    "MULTI_015": "Trong những trường hợp nào việc bị đình chỉ hoặc bị xử phạt nhiều lần có thể dẫn đến thu hồi giấy chứng nhận hoạt động của cơ sở đăng kiểm?",
    "MULTI_016": "Vốn đăng ký thực hiện dự án đầu tư và vốn đầu tư đã thực hiện của dự án được xác định dựa trên những nguồn nào?",
    "MULTI_018": "Khi điều chỉnh chủ trương đầu tư dự án PPP, trình tự thực hiện và thành phần hồ sơ gồm những gì?",
    "MULTI_021": "Khi dự án BOT đường bộ bị giảm doanh thu, nhà đầu tư và bên cho vay phải điều chỉnh phương án tài chính thế nào; nếu doanh thu sau đó tăng cao hơn dự kiến thì xử lý ra sao?",
    "MULTI_022": "Người tham gia bán hàng đa cấp phải lưu giữ giấy tờ gì và từ thời điểm nào mới được tiếp thị, bán hàng hoặc phát triển mạng lưới?",
    "MULTI_027": "Đơn vị khảo sát dự án điện gió ngoài khơi phải đáp ứng yêu cầu năng lực và cam kết về kinh phí như thế nào?",
    "TEMPORAL_001": "Tại ngày 06/02/2025, dự thảo hồ sơ mời thầu được phép lập vào thời điểm nào so với kế hoạch lựa chọn nhà thầu?",
    "TEMPORAL_003": "Tại ngày 01/07/2026, việc mở rộng một trạm dừng nghỉ đã có nhà đầu tư khai thác được chuẩn bị và xác định nghĩa vụ tài chính như thế nào?",
    "TEMPORAL_004": "Tại ngày 15/01/2025, những loại gói thầu nào phục vụ giải phóng mặt bằng, di dời hạ tầng hoặc tái định cư có thể được thực hiện đấu thầu trước?",
    "TEMPORAL_006": "Tại ngày 06/02/2025, chủ đầu tư phải công khai và sửa đổi thông tin về nhà thầu vi phạm trên Hệ thống mạng đấu thầu quốc gia như thế nào?",
}


NEAR_DOMAIN_OOS = [
    {
        "id": "NAT_OOS_001",
        "question": "Doanh nghiệp mới thành lập cần chuẩn bị hồ sơ gì để đăng ký doanh nghiệp lần đầu?",
    },
    {
        "id": "NAT_OOS_002",
        "question": "Thuế suất thuế thu nhập doanh nghiệp áp dụng cho doanh nghiệp có dự án đầu tư được xác định như thế nào?",
    },
    {
        "id": "NAT_OOS_003",
        "question": "Hộ gia đình xin giấy phép xây dựng nhà ở riêng lẻ trong đô thị cần đáp ứng những điều kiện nào?",
    },
    {
        "id": "NAT_OOS_004",
        "question": "Trình tự đăng ký bảo hộ nhãn hiệu cho sản phẩm của một dự án đầu tư được thực hiện như thế nào?",
    },
]


def main() -> None:
    source = json.loads(SOURCE.read_text(encoding="utf-8"))
    by_id = {case["id"]: case for case in source["cases"]}
    cases = []
    category_index: dict[str, int] = {}

    for source_id, question in NATURAL_QUESTIONS.items():
        case = deepcopy(by_id[source_id])
        category = case["category"]
        category_index[category] = category_index.get(category, 0) + 1
        prefix = {
            "single_hop": "NAT_SINGLE",
            "multi_hop": "NAT_MULTI",
            "temporal_aware": "NAT_TEMPORAL",
        }[category]
        case["id"] = f"{prefix}_{category_index[category]:03d}"
        case["question"] = question
        case["notes"] = (
            f"Câu hỏi tự nhiên nháp, kế thừa ground truth từ {source_id}; "
            "cần người duyệt độc lập kiểm tra cách diễn đạt, đáp án, citation và rubric."
        )
        cases.append(case)

    for item in NEAR_DOMAIN_OOS:
        cases.append(
            {
                "id": item["id"],
                "enabled": True,
                "category": "out_of_scope",
                "question": item["question"],
                "expected_statuses": ["refusal"],
                "gold_answer": "",
                "gold_citation_groups": [],
                "answer_rubric": {
                    "required_facts": [],
                    "forbidden_facts": [],
                    "minimum_fact_coverage": 1.0,
                },
                "notes": (
                    "Câu hỏi ngoài phạm vi nhưng gần miền dữ liệu; cần người duyệt "
                    "độc lập xác nhận corpus không chứa căn cứ trả lời."
                ),
            }
        )

    dataset = {
        "name": "AES LUAT natural-language benchmark draft",
        "version": "0.1.0-draft-2026-10-02",
        "validation_profile": "natural_language_draft",
        "description": (
            "50 câu hỏi nháp bằng ngôn ngữ tự nhiên, không nêu sẵn Điều/Khoản/Điểm. "
            "Bộ này tách biệt với benchmark định vị 90 câu và chỉ được dùng chính thức "
            "sau khi có người duyệt độc lập."
        ),
        "created_by": (
            "AI-assisted draft derived from existing ground truth; not an independent "
            "legal benchmark"
        ),
        "reviewed_by": "Chưa duyệt độc lập; không dùng làm kết quả chính thức",
        "cases": cases,
    }
    OUTPUT.write_text(
        json.dumps(dataset, ensure_ascii=False, indent=2) + "\n",
        encoding="utf-8",
    )
    with REVIEW_OUTPUT.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "case_id",
                "category",
                "question",
                "naturalness_ok",
                "neutrality_ok",
                "answer_correct",
                "citation_correct",
                "reviewer",
                "reviewed_at",
                "review_notes",
            ],
        )
        writer.writeheader()
        for case in cases:
            writer.writerow(
                {
                    "case_id": case["id"],
                    "category": case["category"],
                    "question": case["question"],
                    "naturalness_ok": "",
                    "neutrality_ok": "",
                    "answer_correct": "",
                    "citation_correct": "",
                    "reviewer": "",
                    "reviewed_at": "",
                    "review_notes": "",
                }
            )
    print(f"Created {OUTPUT} with {len(cases)} cases.")
    print(f"Created review template {REVIEW_OUTPUT}.")


if __name__ == "__main__":
    main()
