import pdb
import sys
import os
import math
import argparse
import random
import json
import scipy.stats as stats
from pathlib import Path

# make the pyevtsim package accessible
pyEvtSimDir = '../pyevtsim'
sys.path.append(pyEvtSimDir)

# things needed from pyevtsim package

from vrt import VT, VTZero
from rng import sampleExpon, sampleU01
from evt import EvtFunc, EvtMgr

# Capitalize used to code global variables,
# here created with default values

ARRIVAL_RATE = 0.0
PB = 0.0
PS = 0.0
INV_MU1 = 1.0
INV_MU2 = 1.0

SEED = 123456
SERVING_LIMIT = 4 
TERMINATION = 0.0

# START_OBS will be computed to be the time after which measurements
# will be collected for analysis

START_OBS = 0.0
BATCHES = 10

PARAM_DICT = {}

OUTPUT_FILE = 'output.json'
OUTPUT_OBS = []

custStrm = None
filtQueue = None

customerID = 0
def NxtcustomerID():
    global customerID
    customerID += 1
    return customerID


class Customer():
    def __init__(self): 
        # unique customer ID
        self.customerID = NxtcustomerID()
    
    def customerID(self) -> int:
        return self.customerID

# CustomerStream is the process of generating arrivals to the system.
# Poisson arrivals are simulated, but if there are too many admitted
# but as-yet unprocessed customers, the arrival is dropped.

class CustomerStream():
    def __init__(self, arrival_rate, K):

        # Remember the arrival rate, will be needed every time
        # this object schedules the arrival of the next customer.
        #
        self.arrival_rate = arrival_rate

        # Remember the maximum number of customers the model 
        # allows to be in the system concurrently
        #
        self.K = K

        # Accumulate the total number of arrivals during simulation
        self.arrivals = 0

        # Accumulated the total number of arrivals not admitted.
        self.discouraged_arrivals = 0

        # Keep track of number of customers in processing, to be
        # compared with self.K when a new customer arrives
        #
        self.serving_customers = 0

        # Build a trace of customers, when admitted and when departed.
        self.trace = []

    # NewCustomer handles the possibility of including a new arrival into the system, either rejecting it or
    # calling code that passes it to a menu station, and schedules the next
    # arrival.  If the system is full it just schedules the next arrival.

    def NewCustomer(self, only_schedule, none):

        # The parameter 'only_schedule' is True on an initial call
        # made just to schedule the first arrival.  Every subsequent
        # call will treat the event execution as the arrival of a customer.
        # 
        if not only_schedule:
            if self.serving_customers == self.K:
                self.discouraged_arrivals += 1
                self.SaveObs("drop", EvtMgr.NowInSecs(), 0, self.serving_customers)
            else:
                self.arrivals += 1

                cust = Customer()
                # The customer can be admitted to the system.

                self.serving_customers += 1
                self.SaveObs("start", EvtMgr.NowInSecs(), cust.customerID, self.serving_customers)

                filtQueue.ExtArrival(cust)

        # Schedule the next arrival
        # sampling from an exponential probability distribution
        # with rate give at the CustomerStream construction.
        #    Sample the number of seconds until the next arrival,
        # then transform into virtual time format.
        #
        inter_arrival_time = sampleExpon(self.arrival_rate)
        vt_inter_arrival_time = VT.from_secs(inter_arrival_time, pri=1)

        # Frame the scheduling request in an EvtFunc for subsequent scheduling.
        evt_func = EvtFunc(False, None, self.NewCustomer)

        # Schedule the next arrival.
        EvtMgr.AddEvt(evt_func, vt_inter_arrival_time,
                      desc=f"NewCustomer generation")

    # DepartCust is called when a job leaves service and is determined to not branch back

    def DepartCust(self, cust):
        self.serving_customers -= 1
        self.SaveObs("stop", EvtMgr.NowInSecs(), cust.customerID, self.serving_customers)

    # SaveObs is called to save a record of the occurance of an event, but only if the
    # event time is past the time where we begin to save observations, i.e., after we've
    # stop skipping.  When saving the time of the observation, we take a base of the
    # time when observations started as being zero

    def SaveObs(self, msg, time, ID, Msr):
        if START_OBS <= time:
            self.trace.append((msg, time-START_OBS, ID, Msr))

    # ReportArrivals is called when the simulation ends, to report on arrivals.

    def ReportArrivals(self):
        print(f"total arrivals = {self.arrivals}, \
              discouraged arrivals = {self.discouraged_arrivals}")

    # StatReports computes the boundaries of the intervals used in batch means analysis,
    # and then for each interval computes the average of each response variable, taken over that interval.
    # These averages form the samples for the computation of the confidence interval taken around the sample
    # mean.

    def StatReport(self):

        # compute the length of the measurement interval
        interval = (TERMINATION-START_OBS)/BATCHES


        # lists of response variables, sampled over the batch mean intervals

        time_sys      = []      # each element the average time a customer is in the system,
                                # the average being taken over an interval
        accepted_rate  = []     # each element the rate of jobs accepted taken over an interval
        num_sys       = []      # each element the time-averaged number of jobs in the system, taken over an interval
        util_sys      = []      # each element the fraction of time, taken over an interval, when the server is busy with a customer
        drop_pr       = []      # each element the fraction of jobs dropped, taken over an interval

        evts_per_interval = 0
        end_interval = START_OBS-1.0

        # create a list, one element per interval, of lists of observations made in that interval

        batches = []
        for idx in range(0, BATCHES):
            batches.append([])

        # place each observations into the list for the batch in which the observation occurred

        for idx in range(0, len(self.trace)):
            # extract the time of the observation.  Remember the observation start time is time zero
            obs_time = self.trace[idx][1]

            # compute which batch the observation lies in
            batch_num = int(obs_time/interval)

            # append it to the batch's list of observations	
            batches[batch_num].append(self.trace[idx])


        # strictly for information purposes, compute the average number of observations in a batch
        for idx in range(0, len(batches)):
            evts_per_interval += len(batches[idx])
        evts_per_interval /= len(batches)

        # figure out what the number of jobs in system were at the time measurements
        # started to be taken

        prev_n = batches[0][0][3]
        if batches[0][0][0] == 'start':
            prev_n -= 1
        else:
            prev_n += 1

        # compute response variable values for each batch
        for idx in range(0, len(batches)):

            # this_batch will hold the list of observations from this batch,
            # prepended by an 'interval_start' observation at the very beginning
            # with the correct number of jobs in the system at the beginning of the
            # interval and an 'interval_end' observation at the very end, also with
            # the correct number of jobs in system at the end of the interval

            this_batch = []

            # put in a starting event
            #
            if len(batches[idx]) > 0:
                prev_n = batches[idx][0][3]
                if batches[idx][0][0] == 'start':
                    prev_n -=1
                else:
                    prev_n += 1

            this_batch.append(('interval_start', idx*interval, None, prev_n))
            this_batch.extend(batches[idx])

            # put in the final event 

            last_n = this_batch[-1][3]
            this_batch.append(('interval_end', (idx+1)*interval, None, last_n))
            prev_n = last_n

            # initialize variables that are used to compute response values
            num_sys_area = 0.0
            idle_sum = 0.0
            accepted = 0

            # compute the area under the number-in-system curve,
            # and sum of time in interval when the system had no jobs

            for idx in range(1, len(this_batch)):
                interval_n = this_batch[idx-1][3]
                level_time = this_batch[idx][1]-this_batch[idx-1][1]
                num_sys_area += interval_n*level_time
                if this_batch[idx-1][3] == 0:
                    idle_sum += level_time

            # sample of time-averaged number in system over the interval
            num_sys.append(num_sys_area/interval)

            # sample of system utilization over the interval
            util_sys.append(1.0 - idle_sum/interval)

            # determine each customer's time in system using a dictionary that
            # is indexed by the customer's id, and has the time the customer enters.
            # when we see the event where a customer leaves, we can computed the time in system
            # as the difference, and save it in an accumulating total
   
            cust = {}
            sum_time = 0.0
            num_cust_obs = 0
            for obs in this_batch:
                if obs[0] == 'start':
                    cust[obs[2]] = obs[1]
                elif obs[2] in cust and obs[0] == 'stop':
                    sum_time += obs[1]-cust[obs[2]]
                    num_cust_obs += 1
            
            if num_cust_obs > 0:
                time_sys.append(sum_time/num_cust_obs)
            else:
                time_sys.append(0.0)

            # compute the fraction of completing jobs that branch back,
            # and the fraction of arrivals that were dropped

            branches = 0
            drops    = 0
            for idx in range(0, len(this_batch)):
                if this_batch[idx][0] == 'start':
                    accepted += 1
                if this_batch[idx][0] == 'branch':
                    branches += 1
                elif this_batch[idx][0] == 'drop':
                    drops += 1

            if accepted > 0:
                # remember the rate of accepted jobs
                accepted_rate.append( accepted/interval )
                
            if drops+accepted > 0:
                # remember the fraction of jobs dropped on arrival
                drop_pr.append( float(drops)/(accepted+drops) )

        # compute the confidence interval for response variables

        num_sys_mean, num_sys_H = computeCI(num_sys, 0.95)
        accepted_mean, accepted_H = computeCI(accepted_rate, 0.95)
        drop_pr_mean, drop_pr_H = computeCI(drop_pr, 0.95)
        time_sys_mean, time_sys_H = computeCI(time_sys, 0.95)
        util_sys_mean, util_sys_H = computeCI(util_sys, 0.95)

        # print the information for user observation
        print(f"Interval length = {interval}, batches = {BATCHES}, 95% confidence")
        print(f"accepted rate   = {accepted_mean} +/- {accepted_H}, ratio {2*accepted_H/accepted_mean}")
        if drop_pr_mean > 0:
            print(f"drop probability {drop_pr_mean} +/- {drop_pr_H}, ratio {2*drop_pr_H/drop_pr_mean}")
        else:
            print(f"drop probability {0.0} +/- {0}")

        print(f"number in system {num_sys_mean} +/- {num_sys_H}, ratio {2*num_sys_H/num_sys_mean}")
        print(f"time   in system {time_sys_mean} +/- {time_sys_H}, ratio {2*time_sys_H/time_sys_mean}")
        print(f"server util      {util_sys_mean} +/- {util_sys_H}, ratio {2*util_sys_H/util_sys_mean}")

        # create a record of all this for the output file
        obs = {'evt_per_interval': evts_per_interval, 'conf_level': 0.95,
               'accepted':accepted_mean, 'accepted_H':accepted_H,\
                'num_sys': num_sys_mean, 'num_sys_H': num_sys_H, \
                'time_sys': time_sys_mean, 'time_sys_H': time_sys_H, \
                'util_sys': util_sys_mean, 'util_sys_H': util_sys_H, \
                'drop_pr': drop_pr_mean, 'drop_pr_H': drop_pr_H}

        # the record for this run joins the confidence intervals with 
        # the command-line arguments used to create this sample
        entry = obs | PARAM_DICT
        OUTPUT_OBS.append(entry)

        with open(OUTPUT_FILE,'w') as wf:
            json.dump(OUTPUT_OBS, wf, indent=4)

def computeCI(m, alpha):
    n = len(m)
    if n < 2:
        raise ValueError("The list must contain at least two elements.")

    # Calculate sample mean
    mean = sum(m) / n

    # Calculate sample variance and standard deviation
    variance = sum((x - mean) ** 2 for x in m) / (n - 1)
    std_dev = math.sqrt(variance)

    # Calculate standard error
    std_error = std_dev / math.sqrt(n)

    # Find the critical t-value
    # degrees of freedom = n - 1
    df = n - 1
    t_critical = stats.t.ppf((1 + alpha) / 2, df)

    # Calculate half-width
    half_width = t_critical * std_error

    return mean, half_width


# A FiltQueue implements the filtered queue of the diagram
class FiltQueue():
    def __init__(self, K, pS, pB, inv_mu1, inv_mu2):
        self.K  = K
        self.pS = pS
        self.pB = pB
        self.inv_mu1 = inv_mu1
        self.inv_mu2 = inv_mu2
        self.inSystem = []

    def sampleService(self):
        if sampleU01() < self.pS:
            return sampleExpon(1.0/self.inv_mu1)
        return self.inv_mu2

    def ExtArrival(self, cust):
        if self.K <= len(self.inSystem):
            return

        self.Enqueue(cust)

    def EnterCustInService(self, cust):
        # put into service immediately
        evt_func = EvtFunc(self, cust, self.EndService)
        service = self.sampleService()
        #print(f"sampled service time {service}")
        vt_service = VT.from_secs(service, pri=1)
        EvtMgr.AddEvt(evt_func, vt_service,
                      desc=f"service completion")

    def Enqueue(self, cust):
        self.inSystem.append(cust)
        if len(self.inSystem) == 1:
            self.EnterCustInService(cust)
   
    def EndService(self, context, data):
        cust = self.inSystem[0]
        self.inSystem = self.inSystem[1:]

        if len(self.inSystem) > 0:
            # put next job into service
            nxt_cust = self.inSystem[0]
            self.EnterCustInService(nxt_cust)

        if sampleU01()  < self.pB:
            self.Enqueue(cust)
            custStrm.SaveObs("branch", EvtMgr.NowInSecs(), cust.customerID, custStrm.serving_customers)
        else:
            custStrm.DepartCust(cust)

# ReportError is called on discovering of some error that halts
# execution, printing a message describing that error and then
# exiting

def ReportError(msg):
    print(msg)
    exit(1)

# Method getArgs sets up the argparse arguments for scanning the command line,
# gets the command line arguments, and validates them.

def getArgs():

    # A number of global variables are set as a result of parsing the command line
    # and need to be declared as global to get that scope correct
    global ARRIVAL_RATE, SERVING_LIMIT, TERMINATION, SEED, \
            PS, PB, INV_MU1, INV_MU2, BATCHES, START_OBS, OUTPUT_OBS, OUTPUT_FILE, \
            PARAM_DICT

    # Declare all the command line arguments that are possible or expected
    parser = argparse.ArgumentParser()
    parser.add_argument(u'-arrival_rate', metavar=u'Poisson arrival rate of new customers',
                        dest=u'arrival_rate', required=True)

    parser.add_argument(
        u'-pS', metavar=u'probability service drawn from exponential', dest='pS', required=True)

    parser.add_argument(
        u'-pB', metavar=u'probability completed service branches back', dest='pB', required=True)

    parser.add_argument(
        u'-inv_mu1', metavar=u'exponential service mean', dest='inv_mu1', required=True)

    parser.add_argument(
        u'-inv_mu2', metavar=u'constant service time', dest='inv_mu2', required=True)

    parser.add_argument(u'-termination', metavar=u'length of simulation run (in seconds)',
                        dest=u'termination', required=True)

    parser.add_argument(u'-skip ', metavar=u'fraction of initial time to skip',
                        dest=u'skip_frac', required=True)

    parser.add_argument(u'-batches ', metavar=u'number of batches to analyze after initialization skip',
                        dest=u'batches', required=True)

    parser.add_argument(u'-K', metavar=u'maximum number of customers that may be in system',
                        dest=u'serving_limit', required=True)

    parser.add_argument(
        u'-seed', metavar=u'random number generator initialization', dest=u'seed', required=False)

    parser.add_argument(
        u'-o', metavar=u'output file', dest=u'output', required=False)

    # Get command line argument file, if present
    cmdline = sys.argv[1:]
    cmdline = []

    # A common technique I use is to put all the command line arguments
    # in a file, one per line, and then on the command line indicate
    # this by a '-is argument_file' command that is identified before
    # argparse is called, and a command-line list is built up from
    # the contents of the argument file

    if len(sys.argv) == 3 and sys.argv[1] == "-is":
        with open(sys.argv[2], "r") as rf:
            for line in rf:
                line = line.strip()
                if len(line) == 0 or line.startswith('#'):
                    continue
                if line.find("#") > -1:
                    cut = line.find("#")
                    line = line[:cut]
                cmdline.extend(line.split())
    else:
        cmdline = sys.argv[1:]

    # The list 'cmdline' is now either what was on the command line,
    # or is built out of what was in the arguments file.  This is passed
    # to the argparse parser

    args = parser.parse_args(cmdline)

    # Various command line arguments are validated now.
    # Typically, to test whether the input string is a floating point
    # number or integer, we use the python try/except mechanism.
    try:
        ARRIVAL_RATE = float(args.arrival_rate)

        # args.arrival_rate passed the 'is it a floating point number' test.
        # It needs also to pass the 'is it a positive number' test
        if not ARRIVAL_RATE > 0.0:
            ReportError(f"Arrival rate {args.arrival_rate} is not positive")

    except:
        print(f"Arrival rate {args.arrival_rate} needs to be positive")
        exit(1)

    PARAM_DICT['-arrival_rate'] = ARRIVAL_RATE

    try: 
        PS = float(args.pS)
        if not 0.0 <= PS <= 1.0:
            ReportError(f"Service probability selection {args.pS} needs to be in [0.0, 1.0]")
    except:
        print(f"Service probability selection {args.pS} needs to be floating point in [0.0, 1.0]")
        exit(1)

    PARAM_DICT['-pS'] = PS

    try: 
        PB = float(args.pB)
        if not 0.0 <= PS <= 1.0:
            ReportError(f"branchback selection {args.pB} needs to be in [0.0, 1.0]")
    except:
        print(f"Service probability selection {args.pB} needs to be floating point in [0.0, 1.0]")
        exit(1)

    PARAM_DICT['-pB'] = PB

    try: 
        INV_MU1 = float(args.inv_mu1)
        if not 0.0 < INV_MU1:
            ReportError(f"Exponential service rate {args.inv_mu1} needs to be positive")
    except:
        print(f"Exponential service rate {args.inv_mu1} needs to be positive floating point number")
        exit(1)

    PARAM_DICT['-inv_mu1'] = INV_MU1
    try: 
        INV_MU2 = float(args.inv_mu2)
        if not 0.0 < INV_MU2:
            ReportError(f"service mean {args.inv_mu2} needs to be positive")
    except:
        print(f"service mean {args.inv_mu2} needs to be positive floating point number")
        exit(1)

    PARAM_DICT['-inv_mu2'] = INV_MU2
    try:
        TERMINATION = float(args.termination)

        # args.termination passed the 'is it a floating point number' test.
        # It needs also to pass the 'is it a positive number' test
        if not TERMINATION > 0.0:
            ReportError(f"Termination time {args.termination} is not positive")

    except:
        print(f"Termination time {args.termination} needs to be positive")
        exit(1)

    PARAM_DICT['-termination'] = TERMINATION
    try:
        SERVING_LIMIT = int(args.serving_limit)

        # args.serving_limit passed the 'is it an integer' test.
        # It needs also to pass the 'is it a positive integer' test
        if not SERVING_LIMIT > 0:
            ReportError(
                f"Customer limit {args.serving_limit} not positive integer")
    except:
        ReportError(f"Customer limit {args.serving_limit} not positive integer")

    PARAM_DICT['-K'] = SERVING_LIMIT

    try:
        skip_frac = float(args.skip_frac)
        if not 0.0 <= skip_frac < 1.0:
            ReportError(
                f"skip fraction {args.skip_frac} needs to be floating point in [0.0, 1.0)")
    except:
            ReportError(
                f"skip fraction {args.skip_frac} needs to be floating point in [0.0, 1.0)")

    PARAM_DICT['-skip_frac'] = skip_frac

    START_OBS = skip_frac*TERMINATION

    try:
        BATCHES = int(args.batches)
        if not 0 < BATCHES:
            ReportError(
                f"number of batches {args.batches} needs to be positive integer")
    except:
            ReportError(
                f"number of batches {args.batches} needs to be positive integer")

    PARAM_DICT['-batches'] = BATCHES
    if args.seed is not None:
        SEED = args.seed
    random.seed(SEED)

    PARAM_DICT['-seed'] = SEED
    if args.output is not None:
        OUTPUT_FILE = args.output
        # make sure that directory holding this file exists
        parent_dir = Path(OUTPUT_FILE).parent
        if not parent_dir.is_dir():
            ReportError(
                f"directory for output file {args.output} does not exist")

    # if the directory exists but the file does not, initilialize it
    file_path = Path(OUTPUT_FILE)
    if not file_path.is_file():
        output_dict = {}
        try:
            with open(OUTPUT_FILE,'w') as wf:
                json.dump(output_dict, wf, indent=4)
        except:
            ReportError(
                f"Unable to write to output file {OUTPUT_FILE}")
    try:
        # if there are observations in the output file already, load them into OUTPUT_OBS,
        # otherwise initialize it to be an empty list
        with open(OUTPUT_FILE, 'r') as rf:
            output_obs = json.load(rf)
            if len(output_obs) == 0:
                output_obs = []
            OUTPUT_OBS = output_obs 

    except:
            ReportError(
                f"Unable to read output file {OUTPUT_FILE}")

def main():
    # the pointer to the customer stream needs to be global
    # because the constructor of the pickup station needs to
    # reference its departCust method.
    #
    global custStrm, filtQueue

    # getArgs brings in the command line arguments
    # and sets values for global variables used in 
    # various object's constructors.
    getArgs()

    # start the random number stream with the specified seed,
    # this call needs to be made before any calls to the python
    # random number generators.
    #
    random.seed(SEED)

    # Create an object that generates a stream of customers.
    # The object needs to be created before the call to BuildTopo
    # because the PickupStation constructor parameters include a
    # pointer to the custStrm
    #
    custStrm = CustomerStream(ARRIVAL_RATE, SERVING_LIMIT)

    # Schedule the first customer arrival, after one sampled
    # inter-arrival delay.
    #
    custStrm.NewCustomer(True, None)

    # build the queue
    filtQueue = FiltQueue(SERVING_LIMIT, PS, PB, INV_MU1, INV_MU2)

    # Start the execution time of the simulation, to advance under
    # the input parameter giving the end simulation time 'TERMINATION'
    # is reached.
    #
    EvtMgr.Run(TERMINATION)

    # Now that the simulation run has finished, report statistics.
    # First the statistics on the number of arrivals and discouraged arrivals.
    #
    custStrm.ReportArrivals()

    # Now report on the overall delay experienced by a customer,
    # from arrival to departure.
    #
    custStrm.StatReport()


# Press the green button in the gutter to run the script.
if __name__ == '__main__':
    main()

