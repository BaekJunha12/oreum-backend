"""기획안 API 가 돌려주는 모양. 프론트 타입처럼 id 는 글자, 칸 이름은 camelCase 예요."""


def plan_file_payload(doc):
    """프론트 PlanFile { id, name, size, type, pages, url? }. 파일은 공개 주소가 없어서 url 은 안 보내요."""
    return {
        'id': str(doc.pk),
        'name': doc.file_name,
        'size': doc.file_size,
        'type': doc.mime_type,
        'pages': doc.page_count,  # 모르면 null
    }
