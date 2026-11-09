{{- define "triage.name" -}}{{ .Release.Name }}-triage-agent{{- end -}}
{{- define "triage.labels" -}}
app.kubernetes.io/name: triage-agent
app.kubernetes.io/instance: {{ .Release.Name }}
app.kubernetes.io/version: {{ .Chart.AppVersion | quote }}
{{- end -}}
{{- define "triage.selector" -}}
app.kubernetes.io/name: triage-agent
app.kubernetes.io/instance: {{ .Release.Name }}
{{- end -}}
