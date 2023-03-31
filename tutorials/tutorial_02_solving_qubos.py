#!/usr/bin/env python
# coding: utf-8

# *Copyright (C) 2022 Intel Corporation*<br>
# *SPDX-License-Identifier: BSD-3-Clause*<br>
# *See: https://spdx.org/licenses/*
# 
# ---
# 
# # Quadratic Unconstrained Binary Optimization (QUBO) with Lava
# 
# In previous work, we found that our first generation Loihi 1 chip can solve QUBOs more than 17x faster and more than 670x more energy efficient than the CPU-based solver QBSolv [1], which "executes in two-thirds of the time of the best previously known implementation" [2]. Lava translates this solver to Loihi 2 to exploit this chip's higher speed, efficiency, and new hardware features designed for optimization.
# 
# This tutorial ramps up users who want to use Lava's solver for quadratic unconstraint binary optimization (QUBO) problems. It starts with an intuitive description of the algorithm behind the solver, before it exemplifies how to encode and solve a QUBO workload with 700 variables on CPU and Loihi2. An outlook will finally give a glimpse into the future feature releases of the Lava solver. 
# 
# An accompanying tutorial will soon be released to provide a more technical deep dive into Lava's QUBO solver.

# ## Recommended tutorials before starting
# 
# - [Installing Lava](https://github.com/lava-nc/lava/blob/main/tutorials/in_depth/tutorial01_installing_lava.ipynb "Tutorial on Installing Lava")

# ## Set up the environment

# To solve QUBOs in Lava, we import the corresponding modules.

# In[1]:


def setup():
    import os
    #os.environ["KMP_DUPLICATE_LIB_OK"]="TRUE"
    #os.environ["LAVA_PURE_PYTHON"]="1"
    # Interface for QUBO problems
    from lava.lib.optimization.problems.problems import QUBO
    # Generic optimization solver
    from lava.lib.optimization.solvers.generic.solver import OptimizationSolver, solve, SolverConfig
    import timeit


    # In addition, we import auxiliary modules to generate the workloads and run the solver.

    # In[2]:


    import os
    import numpy as np
    import networkx as ntx


    # If Loihi 2 hardware is available, we can take advantage of the large speed and energy efficiency of this chip to solve QUBOs. To access the chip, we must configure the following environment variables:

    # In[3]:


    from lava.utils.system import Loihi2
    Loihi2.preferred_partition = "oheogulch"
    loihi2_is_available = Loihi2.is_loihi2_available

    if loihi2_is_available:
        # Enable SLURM, the workload manager used to distribute Loihi2 resources to users
        os.environ['SLURM'] = '1'


    # ## An intuitive description of Lava's QUBO solver

    # A quadratic unconstrained binary optimization (QUBO) task is an NP-hard combinatorial optimization problem with a plethory of commercial applications, as exemplified later. Loihi offers a range of features useful for their fast and energy efficient solution.

    # #### The QUBO formalism

    # The goal of a QUBO is to minimize the cost function
    # 
    # &emsp;&emsp; $\underset{x}{\text{min}}\; \mathbf{x}^T \mathbf{Q} \mathbf{x} $ ,
    # 
    # which is subject to no constraints. This equation is defined by the QUBO matrix $\mathbf{Q}\in\mathbb{R}^{n\times n}$ and the vector of binary variables, $\mathbf{x} \in \{0,1\}^n$ .

    # #### Lava's QUBO solver

    # To solve QUBOs, Lava currently implements a spiking version of a Boltzmann machine that was inspired by the work of Jonke et al. [2].
    # 
    # To give a rough intuition of the solver, it represents binary variables as neurons that either spike (variable value=1) or are silent (value=0).
    # 
    # <br>
    # 
    # <img src="https://user-images.githubusercontent.com/86950058/192372805-b974e39b-fae8-4a68-810b-f52a9363987b.png" width="500" align="center"/>
    #     
    # Each neuron has an internal state representing the probability that the neuron should spike. When the state exceeds a threshold, the neuron spikes and the variable is thus switched to 1. Once a spike occurs at neuron $i$, the synapses forward the spikes according to the off-diagonal QUBO weights $Q_{ij}$ to other neurons $j$. Negative weights increase the chance that the connected neuron will spike, positive weights decrease the chance. <br>
    # On-diagonal weights $Q_{ii}$ add a bias to the neurons state variable, which continuously increases the chance that the neuron will spike.
    # 
    # <br>
    # 
    # <img src="https://user-images.githubusercontent.com/86950058/192372894-a6f757e5-a6bf-47bb-8254-08de9188d029.png" width="800"  align="center"/>

    # ## Example application: finding the Maximum Independent Set of a graph

    # The following example shows how to formulate and solve a problem as QUBO, using the NP-hard maximum independent set (MIS) problem from graph theory. The goal of an MIS task is to find the largest subset of vertices in a graph that are mutually unconnected. In the following graph, the purple nodes form such a set:
    # 
    # <br>
    # 
    # <img src="https://user-images.githubusercontent.com/86950058/192372990-ec4e5926-463c-4b30-810d-08a896446d8a.png" width="250"/>

    # Hardware accelerators for this problem class are subject to substantial research efforts [3, 4] due to the large industrial need, as recently summarized by Wurtz et al. [5] and exemplified in the following figure.

    # <img src="https://user-images.githubusercontent.com/86950058/197763251-c6e5929d-587e-400a-8392-f398d5176f7e.png" width="800"/>
    # 
    # *a) For wireless communication such as 5G or WiFi, access points and sensors are grouped into small networks. To avoid interference, MIS can help to divide the networks into almost interference-free groups that may use the same frequencies [6]. <br>
    # b) To find the largest error-correcting code, each binary vector $u_i$ is considered as the vertex of a graph. Two vertices $u_i$ and $u_j$ are joined by an edge if both vectors may end up in the same state if acted upon by certain errors, such as deletion or transposition of bits. The MIS describes the largest code that is robust to such errors [7]. <br>
    # c) In the design of semiconductor chips, a via connects two adjacent net segments in adjacent metal layers. Redundant vias are inserted to tolerate single via failures and thus improving the manufacturing yield [8]. If a specific via can be replaced by a redundant double via, it is modeled as a vertex. If two vias cannot be simultaneously replaced by double vias due to design rule violations, their vertices are connected by an edge. The MIS determines the most reliable chip design with the maximum number of redundant vias.*

    # The following code determines the MIS for a graph with 1000 nodes. For this, it translates the MIS problem into a QUBO workload, and then solves it in Lava.

    # #### Define the QUBO workload

    # Lava provides an easy interface to encode QUBO problems, by providing the QUBO matrix $\mathbf{Q}$.

    # In[4]:


    # Import utility functions to create and analyze MIS workloads
    from lava.lib.optimization.utils.generators.mis import MISProblem

    # Create an undirected graph with 1000 vertices and a 
    # probability of 85% that any two vertices are randomly connected
    mis = MISProblem(num_vertices=955, connection_prob=0.9, seed=44)

    # Translate the MIS problem for this graph into a QUBO matrix
    q = mis.get_qubo_matrix(w_diag=1, w_off=8)

    # Create the qubo problem
    qubo_problem = QUBO(q)


    # #### Solve the QUBO on a CPU or Loihi 2

    # The QUBO matrix is provided to Lava's generic _OptimizationSolver_ for constraint optimization problems. A call to its _solve_ method then tackles the workload.
    # 
    # As stopping condition, you can provide the solver with a maximum number of time steps (_timeout_) and/or a target cost.
    # 
    # Lava will print an obtained solution whenever it found a local minimum. Then it continues its search until either stopping condition is fullfilled.
    # 
    # The following cell will run the solver either on a CPU backend, or on a Loihi 2 chip if available. The solutions may differ, due to slightly different noise models.

    # In[5]:

    solver = OptimizationSolver(qubo_problem)

    # In[ ]:

    # Provide hyperparameters for the solver
    # Guidance on the hyperparameter search will be provided in the deep dive tutorial
    np.random.seed(85134)
    hyperparameters = {
        "temperature": int(1),
        "noise_precision": int(16),
        "refract": np.random.randint(5, 20, qubo_problem.num_variables),}

    if loihi2_is_available:
        backend = 'Loihi2'
    else:
        backend = 'CPU'

    return hyperparameters, backend, solver, mis, qubo_problem
# In[ ]:


def run(hyperparameters, backend, solver, solution_loihi):
    from lava.lib.optimization.solvers.generic.solver import SolverConfig
    import numpy as np
    # Solve the QUBO using Lava's OptimizationSolver on CPU
    # Change "backend='Loihi2'" if your system has physical access to this chip
    solver_report = solver.solve(
        config=SolverConfig(
            timeout=10000,
            hyperparameters=hyperparameters,
            target_cost=int(-5),
            backend=backend
        )
    )
    # In[ ]:

    solution_loihi = solver_report.best_state
    print(f'\nSolution of the provided QUBO: {np.where(solution_loihi == 1.)[0]}.')


# In[ ]:





# In[ ]:

if __name__ == '__main__':
    import timeit
    from __main__ import setup, run
    hyperparams = None
    solver = None
    backend = None
    solution_loihi = None
    hyperparams, backend, solver, mis, qubo_problem = setup()
    print(timeit.timeit("run(hyperparams, backend, solver, solution_loihi)", setup="from __main__ import run, hyperparams, backend, solver, solution_loihi", number=3))

# The obtained solution is an optimal solution of the provided QUBO problem. To see this, we can compare it with the result of Python's Networkx package, which solves the underlying graph theoretical problem directly.

# In[ ]:


# Find the optimal solution to the MIS problem
    solution_opt = mis.find_maximum_independent_set()

    # Calculate the QUBO cost of the optimal solution
    cost_opt = qubo_problem.evaluate_cost(solution=solution_opt)

    # Calculate the QUBO cost of Lava's solution
    #cost_lava = qubo_problem.evaluate_cost(solution=solution_loihi)

    #print(f'QUBO cost of solution: {cost_lava} (Lava) vs. {cost_opt} (optimal)\n')
    print(f'QUBO cost of solution: {cost_opt}\n')

# ## Future features 

# Future releases will provide the following advancements and many more:
# - Compiler support for larger problems and faster problem compilation.
# - Performance improvements using advanced hyperparameter search, improved noise annealing schedules, additional algorithms, and parallel runs of solver instances. 
# - Utilities to benchmark energy consumption, run time, and accuracy between Loihi1, Loihi2, and CPU-based state-of-the-art solvers.
# - Support for Loihi1.

# ## How to learn more?
# 
# We will soon release an accompanying deep dive tutorial to explain how...
# - the QUBO solver works under the hood.
# - optimization tasks can be encoded as QUBO.
# - hyperparameters affect the performance of the solver.
# - to benchmark solution accuracy, run time, and energy consumption between Loihi1, Loihi2, and CPU-based solvers.
# 
# Watch this [space](https://github.com/lava-nc/lava-optimization) to learn about upcoming developments to the QUBO solver and the optimization toolbox in Lava in general. 
# 
# If you want to find out more about the implementation of the QUBO solver, have a look at the [Lava documentation](https://lava-nc.org/ "Lava Documentation") or dive into the [source code](https://github.com/lava-nc/lava-optimization/tree/main/src/lava/lib/optimization/solvers/generic/solver.py
# "Source code of the generic constraint optimization solver").
# 
# To receive regular updates on the latest developments and releases of the Lava Software Framework please subscribe to the [INRC newsletter](http://eepurl.com/hJCyhb "INRC Newsletter").

# 
# ## References
# 
# [1] Benchmarks ran with [QBSolv](https://github.com/dwavesystems/qbsolv) on an  Intel Core i9-7920X CPU @ 2.90GHz with 132GB DRAM. <br>
# Performance varies by use, configuration and other factors. Learn more at www.Intel.com/PerformanceIndex. <br>
# Performance results are based on testing as of dates shown in configurations and may not reflect all publicly available updates.  See backup for configuration details.  No product or component can be absolutely secure. 
# 
# [2] D-Wave Systems Inc: Booth, Reinhardt, Roy, _Partitioning Optimization Problems for Hybrid Classical/Quantum Execution_. [Technical report](https://docs.ocean.dwavesys.com/projects/qbsolv/en/latest/_downloads/bd15a2d8f32e587e9e5997ce9d5512cc/qbsolv_techReport.pdf "DWave's technical report"), 2017. <br>
# 
# [3] Mallick, A., Bashar, M.K., Truesdell, D.S., Calhoun, B.H., Joshi, S., Shukla, N. Using synchronized oscillators to compute the maximum independent set. Nature Communications, 11, 2020. <br>
# 
# [4] Ebadi, S., Keesling, A., Cain, M., Wang, T.T., Bluvstein, D., Semeghini, G., Omran, A., Liu, J.-G., Samajdar, R., Luo, X.-Z., Nash, B., Gao, X., Barak, B., Farhi, E., Sachdev, S., Gemelke, N., Zhou, L., Choi, S., Pichler, H., Wang, S.-T., Greiner, M., Vuletic, V.,. Lukin, M.D. Quantum optimization of maximum independent set using Rydberg atom arrays. Science, 376, 6598, 2022. <br>
# 
# [5] Wurtz, J., Lopes, P., Gemelke, N., Keesling, A., Wang, S. Industry applications of neutral-atom quantum computing solving independent set problems. arXiv:2205.08500v1, 2022. <br>
# 
# [6] Zhou, J., Wang, L., Wang, W. & Zhou, Q. Efficient graph-based resource allocation scheme using maximal independent set for randomly-deployed small star networks. Sensors 17, 2553 (2017). <br>
# 
# [7] Butenko, S., Pardalos, P., Sergienko, I., Shylo, V. & Stetsyuk, P. Finding maximum independent sets in graphs arising from coding theory. Proceedings of the 17th ACM Symposium on Applied Computing, 542–546, 2002. <br>
# 
# [8] Lee, K. Y. & Wang, T. C. Post-routing redundant via insertion for yield/reliability improvement. In Proceedings of the 2006 Asia and South Pacific Design Automation Conference, 303–308, 2006. <br>
