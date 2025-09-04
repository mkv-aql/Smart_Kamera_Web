# minimal API contracts

## Upload image

POST /images (multipart)

Response: 
```
{ "image_id": "uuid", "s3_key": "images/uuid.jpg" }
```
## Trigger OCR

POST /ocr/jobs with { "image_id": "uuid" }

Response: 
```
{ "job_id": "uuid" }
```

## Check job status

GET /ocr/jobs/{job_id}

Response: 
```
{ "status": "queued|running|done|error", "progress": 0..100 }
```

## Fetch OCR results

GET /images/{image_id}/results

Response:
```
{
  "items": [
    { "bbox":[x1,y1,x2,y2], "name":"Müller", "confidence":0.82, "id":"row-id" }
  ]
}
```

## Edit a row

PATCH /results/{id} with partial body, e.g. { "name": "Müller-Lüdenscheidt" }

Soft-delete (remove name)

POST /results/{id}/remove

Response: 
```
{ "ok": true }
```
(or mark deleted=true to keep an audit trail)

## Export CSV

GET /images/{image_id}/export → returns a CSV file.