ARG EMR_VERSION=emr-6.15.0
FROM public.ecr.aws/emr-on-eks/spark/${EMR_VERSION}
USER root

RUN mkdir -p /usr/lib/poc
COPY custom-entrypoint.sh /usr/lib/poc/entrypoint.sh
RUN chown -R hadoop:hadoop /usr/lib/poc
RUN chmod -R a+x /usr/lib/poc

USER hadoop:hadoop
ENTRYPOINT ["/usr/lib/poc/entrypoint.sh"]