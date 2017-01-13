import os
import sys
import time
import string
import subprocess
from itertools import islice
from functools import partial
from multiprocessing.dummy import Pool, Lock
from cdis_pipe_utils import pipe_util
from cdis_pipe_utils import time_util
from cdis_pipe_utils import postgres
from tools.postgres import MuTect as MuTect

def do_pool_commands(cmd, case_id, engine, logger, files, lock = Lock()):
    logger.info('running mutect2_vc chunk call: %s' % cmd)
    output = subprocess.Popen(cmd, shell=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    output_stdout = output.communicate()[1]
    with lock:
        logger.info('contents of output=%s' % output_stdout.decode().format())
        cmd_list = cmd.split()
        toolname = ('mutect2_variant_call: %s' % cmd_list[18])
        metrics = time_util.parse_time(output_stdout)
        met = MuTect(case_id = case_id,
                    tool = toolname,
                    files=files,
                    systime=metrics['system_time'],
                    usertime=metrics['user_time'],
                    elapsed=metrics['wall_clock'],
                    cpu=metrics['percent_of_cpu'],
                    max_resident_time=metrics['maximum_resident_set_size'])

        postgres.create_table(engine, met)
        postgres.add_metrics(engine, met)
        logger.info('completed mutect2_vc chunk call: %s' % str(cmd))
    return output.wait()

def multi_commands(case_id, cmds, thread_count, engine, files, logger):
    pool = Pool(int(thread_count))
    output = pool.map(partial(do_pool_commands, case_id=case_id, engine=engine, logger=logger, files=files), cmds)
    return output

def fai_chunk(fai_path, blocksize):
  seq_map = {}
  with open(fai_path) as handle:
    head = list(islice(handle, 25))
    for line in head:
      tmp = line.split("\t")
      seq_map[tmp[0]] = int(tmp[1])
    for seq in seq_map:
        l = seq_map[seq]
        for i in range(1, l, blocksize):
            yield (seq, i, min(i+blocksize-1, l))

def mutect2_cmd_template(gatk_path, ref, fai_path, blocksize, java_heap, pon, cosmic, dbsnp, output_base, contEst, normal_bam_path, tumor_bam_path, mode):
    if not mode:
        template = string.Template("/usr/bin/time -v java -Djava.io.tmpdir=/tmp/job_tmp_${BLOCK_NUM} -d64 -jar -Xmx${JAVA_HEAP} -XX:+UseSerialGC ${GATK_PATH} -T MuTect2 -nct 1 -nt 1 -R ${REF} -L ${REGION} -I:tumor ${TUMOR_BAM} -I:normal ${NORMAL_BAM} --normal_panel ${PON} --cosmic ${COSMIC} --dbsnp ${DBSNP} --contamination_fraction_to_filter ${CONTAMINATION} -o ${OUTPUT_BASE}.${BLOCK_NUM}.mt2.vcf --output_mode EMIT_VARIANTS_ONLY --disable_auto_index_creation_and_locking_when_reading_rods")
    else:
        template = string.Template("/usr/bin/time -v java -Djava.io.tmpdir=/tmp/job_tmp_${BLOCK_NUM} -d64 -jar -Xmx${JAVA_HEAP} -XX:+UseSerialGC ${GATK_PATH} -T MuTect2 -nct 1 -nt 1 -R ${REF} -L ${REGION} -I:tumor ${TUMOR_BAM} -I:normal ${NORMAL_BAM} --normal_panel ${PON} --cosmic ${COSMIC} --dbsnp ${DBSNP} --contamination_fraction_to_filter ${CONTAMINATION} -o ${OUTPUT_BASE}.${BLOCK_NUM}.mt2.vcf --output_mode EMIT_VARIANTS_ONLY --disable_auto_index_creation_and_locking_when_reading_rods --dontUseSoftClippedBases")
    for i, block in enumerate(fai_chunk(fai_path, blocksize)):
        cmd = template.substitute(dict(REF = ref, REGION = '%s:%s-%s' % (block[0], block[1], block[2]), BLOCK_NUM = i),
                                       GATK_PATH = gatk_path,
                                       JAVA_HEAP = java_heap,
                                       NORMAL_BAM = normal_bam_path,
                                       TUMOR_BAM = tumor_bam_path,
                                       CONTAMINATION = contEst,
                                       PON = pon,
                                       COSMIC = cosmic,
                                       DBSNP = dbsnp,
                                       OUTPUT_BASE = output_base)
        yield cmd, "%s.%s.mt2.vcf" % (output_base, i)

def run_mutect(case_id, normal_id, normal_bam_path, tumor_id, tumor_bam_path, known_snp_vcf_path, cosmic_path, thread_count, java_heap, reference_fasta_path, contEst, pon_path, fai_path, blocksize, engine, logger, mode):
  files = [normal_id, tumor_id]
  step_dir = os.path.join(os.getcwd(), 'mutect2')
  os.makedirs(step_dir, exist_ok=True)
  merge_dir = os.getcwd()
  os.makedirs(merge_dir, exist_ok=True)
  tumor_bam_name = os.path.basename(tumor_bam_path)
  bam_base, bam_ext = os.path.splitext(tumor_bam_name)
  out_vcf = os.path.join(merge_dir, bam_base) + '_mutect2.vcf'
  logger.info('mutect2_vcf=%s' % out_vcf)
  if pipe_util.already_step(step_dir, case_id + '_MuTect2_VC', logger):
    logger.info('already completed step `MuTect2 Variant Calling` of: %s and %s' % (normal_bam_path, tumor_bam_path))
  else:
    logger.info('running step `MuTect2 Variant Calling` of: %s and %s' % (normal_bam_path, tumor_bam_path))
    #home_dir = os.path.expanduser('~')
    gatk_path = os.path.join('/home/ubuntu', 'tools', 'GenomeAnalysisTK.jar')
    cmds = list(mutect2_cmd_template(
                                   mode = mode,
                                   gatk_path = gatk_path,
                                   ref = reference_fasta_path,
                                   fai_path = fai_path,
                                   blocksize = blocksize,
                                   java_heap = java_heap,
                                   normal_bam_path = normal_bam_path,
                                   tumor_bam_path = tumor_bam_path,
                                   contEst = contEst,
                                   pon = pon_path,
                                   cosmic = cosmic_path,
                                   dbsnp = known_snp_vcf_path,
                                   output_base = os.path.join(step_dir, 'output'))
    )
    outputs = multi_commands(case_id, list(a[0] for a in cmds), thread_count, engine, files, logger)
    first = True
    with open (out_vcf, "w") as ohandle:
      for cmd, out in cmds:
        with open(out) as handle:
          for line in handle:
            if first or not line.startswith('#'):
              ohandle.write(line)
        first = False
    pipe_util.create_already_step(step_dir, case_id + '_MuTect2_VC', logger)
    logger.info('completed running step `MuTect2 Variant Calling` of: %s and %s' % (normal_bam_path, tumor_bam_path))
  return