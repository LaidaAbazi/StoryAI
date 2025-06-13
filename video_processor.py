def get_video_id(url: str) -> str:
    """Extract video ID from HeyGen URL."""
    try:
        # Handle HeyGen URL format: https://app.heygen.com/videos/{video_id}
        if 'app.heygen.com/videos/' in url:
            return url.split('/videos/')[-1].strip()
        return url.strip()
    except Exception as e:
        logger.error(f"Error extracting video ID from URL: {e}")
        return url.strip() 