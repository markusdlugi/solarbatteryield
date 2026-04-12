# DynamoDB Setup für Short URLs

Diese Anleitung beschreibt die Einrichtung der DynamoDB-Tabelle für URL-Shortening.

## Umgebungsvariablen

Die App benötigt folgende Umgebungsvariablen für die DynamoDB-Anbindung:

| Variable                          | Beschreibung              | Beispiel           |
|-----------------------------------|---------------------------|--------------------|
| `SOLARBATTERYIELD_DYNAMODB_TABLE` | Name der DynamoDB-Tabelle | `solarbatteryield` |
| `AWS_DEFAULT_REGION`              | AWS Region                | `eu-central-1`     |
| `AWS_ACCESS_KEY_ID`               | AWS Access Key ID         | `AKIA...`          |
| `AWS_SECRET_ACCESS_KEY`           | AWS Secret Access Key     | `wJal...`          |

**Hinweis:** Wenn die App auf AWS (z.B. EC2, ECS, Lambda) läuft, können stattdessen IAM Roles verwendet werden. In
diesem Fall sind `AWS_ACCESS_KEY_ID` und `AWS_SECRET_ACCESS_KEY` nicht erforderlich.

## DynamoDB-Tabelle erstellen

### Via AWS Console

1. Gehe zu DynamoDB → Tables → Create table
2. Konfiguriere:
    - **Table name:** `solarbatteryield`
    - **Partition key:** `PK` (String)
    - **Sort key:** `SK` (String)
    - **Table settings:** On-demand capacity (empfohlen für geringe Last)
3. Unter "Additional settings" → Time to Live (TTL):
    - **TTL attribute name:** `ExpireAt`

### Via AWS CLI

```bash
# Tabelle erstellen (mit Sort Key für Single-Table Design)
aws dynamodb create-table \
    --table-name solarbatteryield \
    --attribute-definitions \
        AttributeName=PK,AttributeType=S \
        AttributeName=SK,AttributeType=S \
    --key-schema \
        AttributeName=PK,KeyType=HASH \
        AttributeName=SK,KeyType=RANGE \
    --billing-mode PAY_PER_REQUEST \
    --region eu-central-1

# TTL aktivieren (automatische Löschung nach 3 Monaten)
aws dynamodb update-time-to-live \
    --table-name solarbatteryield \
    --time-to-live-specification Enabled=true,AttributeName=ExpireAt \
    --region eu-central-1
```

### Via Terraform

```hcl
resource "aws_dynamodb_table" "solarbatteryield" {
  name         = "solarbatteryield"
  billing_mode = "PAY_PER_REQUEST"
  hash_key     = "PK"
  range_key    = "SK"

  attribute {
    name = "PK"
    type = "S"
  }

  attribute {
    name = "SK"
    type = "S"
  }

  ttl {
    attribute_name = "ExpireAt"
    enabled        = true
  }

  tags = {
    Application = "solarbatteryield"
    Environment = "production"
  }
}
```

## IAM Policy (Minimal Permissions)

Erstelle eine IAM Policy mit nur den notwendigen Rechten:

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Sid": "SolarbatteryieldDynamoDB",
      "Effect": "Allow",
      "Action": [
        "dynamodb:PutItem",
        "dynamodb:Query",
        "dynamodb:DescribeTable"
      ],
      "Resource": "arn:aws:dynamodb:eu-central-1:ACCOUNT_ID:table/solarbatteryield"
    }
  ]
}
```

**Ersetze `ACCOUNT_ID` mit deiner AWS Account ID und `eu-central-1` mit deiner Region.**

### Berechtigungen erklärt

| Aktion                   | Zweck                                           |
|--------------------------|-------------------------------------------------|
| `dynamodb:PutItem`       | Neue Konfigurationen speichern                  |
| `dynamodb:Query`         | Konfigurationen anhand des Short-Keys laden     |
| `dynamodb:DescribeTable` | Verbindungstest beim Start der App              |

**Nicht benötigt:**

- `dynamodb:Scan` – Kein Durchsuchen der Tabelle
- `dynamodb:DeleteItem` – Löschung erfolgt automatisch via TTL
- `dynamodb:UpdateItem` – Konfigurationen werden nie aktualisiert
- `dynamodb:GetItem` – Query wird stattdessen verwendet (für SK-Flexibilität)

## IAM User erstellen (empfohlen für Streamlit Cloud)

```bash
# User erstellen
aws iam create-user --user-name solarbatteryield-app

# Policy erstellen (speichere obige JSON als policy.json)
aws iam create-policy \
    --policy-name SolarbatteryieldDynamoDBAccess \
    --policy-document file://policy.json

# Policy an User anhängen
aws iam attach-user-policy \
    --user-name solarbatteryield-app \
    --policy-arn arn:aws:iam::ACCOUNT_ID:policy/SolarbatteryieldDynamoDBAccess

# Access Keys erstellen
aws iam create-access-key --user-name solarbatteryield-app
```

Die ausgegebenen Access Keys (`AccessKeyId` und `SecretAccessKey`) in den Umgebungsvariablen der App hinterlegen.

## Tabellenstruktur

Die Tabelle verwendet ein Single-Table Design mit Prefixes für zukünftige Erweiterbarkeit.

### Schema

| Attribut     | Typ    | Format                    | Beschreibung                                                        |
|--------------|--------|---------------------------|---------------------------------------------------------------------|
| `PK`         | String | `SIM#<short_key>`         | Partition Key mit Prefix und 8-stelligem zufälligem Short-Key       |
| `SK`         | String | `CONFIG#<created_at>`     | Sort Key mit Prefix und Unix-Timestamp der Erstellung               |
| `ConfigData` | String | Base64                    | Komprimierte, base64-kodierte Konfiguration                         |
| `ExpireAt`   | Number | Unix-Timestamp            | Automatische Löschung nach 3 Monaten (90 Tage)                      |

### Beispiel-Item

```json
{
  "PK": "SIM#AbC2xY8z",
  "SK": "CONFIG#1712937600",
  "ConfigData": "eJwrySxK1M1NzSsBABNfA/o=",
  "ExpireAt": 1720713600
}
```

### Key-Design

- **Prefixes:** `SIM#` und `CONFIG#` ermöglichen später weitere Entitätstypen in derselben Tabelle
- **Short-Key:** 8 Zeichen aus Base57-Alphabet (ohne 0/O/1/l/I für bessere Lesbarkeit)
- **Entropie:** 57^8 ≈ 111 Billionen Kombinationen (~46.8 Bits) – sicher gegen Enumeration
- **Sort Key:** Enthält Erstellungs-Timestamp für potenzielle Versionierung

## Fallback-Verhalten

Falls DynamoDB nicht erreichbar ist (keine Credentials, Netzwerkfehler, etc.):

- Die App generiert automatisch lange URLs mit eingebetteter Konfiguration (`?cfg=...`)
- Kein Fehler für den Nutzer
- Volle Funktionalität bleibt erhalten

## Troubleshooting

### "You must specify a region"

→ `AWS_DEFAULT_REGION` Umgebungsvariable setzen

### "Unable to locate credentials"

→ `AWS_ACCESS_KEY_ID` und `AWS_SECRET_ACCESS_KEY` prüfen

### "AccessDeniedException"

→ IAM Policy prüfen, insbesondere Region und Table-Name im ARN

### Nur lange URLs werden generiert

→ Logs prüfen: `WARNING solarbatteryield.persistence: DynamoDB connection failed: ...`


